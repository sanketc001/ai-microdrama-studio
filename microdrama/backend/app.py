"""FastAPI backend for the AI Microdrama Studio.

Wires the director LLM, preset library, session/timeline state, and the
single-GPU job queue into one API the React frontend consumes. Generated media
is served from /media (the project's outputs/ dir).
"""
from __future__ import annotations

import copy
import shutil
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import config
from ..director import DirectorLLM
from ..presets import store as presets
from . import jobs, sessions

config.ensure_dirs()
app = FastAPI(title="AI Microdrama Studio")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=str(config.OUTPUTS_DIR)), name="media")

_director: DirectorLLM | None = None


def get_director() -> DirectorLLM:
    global _director
    if _director is None:
        _director = DirectorLLM()
    return _director


def media_url(path: str | None) -> str | None:
    if not path:
        return None
    try:
        rel = Path(path).resolve().relative_to(config.OUTPUTS_DIR.resolve())
        return "/media/" + str(rel).replace("\\", "/")
    except Exception:
        return None


def serialize_session(s: dict) -> dict:
    s = copy.deepcopy(s)
    s["video_url"] = media_url(s.get("video"))
    s["music_url"] = media_url(s.get("music"))
    for sc in s.get("scenes", []):
        sc["image_url"] = media_url(sc.get("image"))
        sc["audio_url"] = media_url(sc.get("audio"))
        sc["sfx_url"] = media_url(sc.get("sfx"))
    return s


def _save_upload(file: UploadFile, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    return dest


# --- health ----------------------------------------------------------------
@app.get("/api/health")
def health():
    from ..comfy import ComfyClient
    return {"ok": True, "comfyui": ComfyClient().is_up(), "llm": config.LLM_MODEL}


# --- presets ----------------------------------------------------------------
@app.get("/api/presets")
def get_presets():
    data = presets.all_presets()
    # expose generated asset paths as servable /media URLs
    for c in data.get("characters", []):
        if c.get("image"):
            c["image"] = media_url(c["image"]) or c["image"]
        if c.get("voice_sample"):
            c["voice_sample"] = media_url(c["voice_sample"]) or c["voice_sample"]
    for s in data.get("scenes", []):
        if s.get("image"):
            s["image"] = media_url(s["image"]) or s["image"]
    for v in data.get("voices", []):
        if v.get("sample"):
            v["sample"] = media_url(v["sample"]) or v["sample"]
    return data


@app.post("/api/presets/{kind}")
def add_preset(kind: str, item: dict = Body(...)):
    if kind not in presets.KINDS:
        raise HTTPException(404, f"unknown preset kind {kind}")
    return presets.add(kind, item)


@app.put("/api/presets/{kind}/{item_id}")
def update_preset(kind: str, item_id: str, patch: dict = Body(...)):
    res = presets.update(kind, item_id, patch)
    if res is None:
        raise HTTPException(404, "preset not found")
    return res


@app.delete("/api/presets/{kind}/{item_id}")
def delete_preset(kind: str, item_id: str):
    return {"deleted": presets.delete(kind, item_id)}


# --- sessions ---------------------------------------------------------------
class CreateSession(BaseModel):
    title: str = "Untitled"
    premise: str = ""
    frame_rate: int = 24
    propose: bool = True


@app.post("/api/sessions")
def create_session(body: CreateSession):
    s = sessions.create(body.title, body.premise, body.frame_rate)
    if body.premise and body.propose:
        try:
            chars = presets.load("characters")
            scns = presets.load("scenes")
            s["story"] = get_director().propose_story(body.premise, characters=chars, scenes=scns)
            if s["story"].get("title") and s["title"] == "Untitled":
                s["title"] = s["story"]["title"]
            sessions.save(s)
        except Exception as exc:  # noqa: BLE001
            s["story_error"] = str(exc)
    return serialize_session(s)


@app.get("/api/sessions")
def list_sessions():
    return sessions.list_sessions()


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    s = sessions.get(sid)
    if not s:
        raise HTTPException(404, "session not found")
    return serialize_session(s)


@app.delete("/api/sessions/{sid}")
def delete_session(sid: str):
    return {"deleted": sessions.delete(sid)}


class PatchSession(BaseModel):
    title: str | None = None
    global_prompt: str | None = None
    frame_rate: int | None = None


@app.patch("/api/sessions/{sid}")
def patch_session(sid: str, body: PatchSession):
    s = sessions.require(sid)
    for k, v in body.model_dump(exclude_none=True).items():
        s[k] = v
    return serialize_session(sessions.save(s))


@app.post("/api/sessions/{sid}/branch")
def branch_session(sid: str):
    """Deep-copy this session as a new take to explore alternatives."""
    return serialize_session(sessions.branch(sid))


@app.post("/api/sessions/{sid}/continue")
def continue_session(sid: str):
    """Start a new session seeded with this one's final rendered frame, so the
    story continues with visual continuity; the director proposes what's next."""
    s = sessions.require(sid)
    if not s.get("video"):
        raise HTTPException(400, "render this session first, then continue")
    new = sessions.create((s.get("title") or "Untitled") + " ▸ next",
                          premise=s.get("premise", ""),
                          frame_rate=int(s.get("frame_rate", 24)), parent_id=sid)
    new["global_prompt"] = s.get("global_prompt", "")
    from ..video_util import extract_last_frame
    frame = extract_last_frame(s["video"], sessions.session_asset_dir(new["id"]) / "continue_from.png")
    sc = sessions.new_scene("image", prompt="the story continues", seconds=3.0, image=str(frame))
    if s.get("scenes"):
        sc["character_ids"] = list(s["scenes"][-1].get("character_ids", []))
    new["scenes"] = [sc]
    try:
        new["story"] = get_director().expand_choice(
            s.get("story", {}), "Continue the story from the final shot shown in the image.")
    except Exception as exc:  # noqa: BLE001
        new["story_error"] = str(exc)
    return serialize_session(sessions.save(new))


# --- director ---------------------------------------------------------------
@app.post("/api/sessions/{sid}/steer")
def steer(sid: str, body: dict = Body(...)):
    s = sessions.require(sid)
    s["story"] = get_director().expand_choice(s.get("story", {}), body.get("input", ""))
    return serialize_session(sessions.save(s))


@app.post("/api/sessions/{sid}/compile")
def compile_timeline(sid: str):
    s = sessions.require(sid)
    timeline = get_director().compile_timeline(s.get("story") or {"premise": s.get("premise")})
    if timeline.get("global_prompt"):
        s["global_prompt"] = timeline["global_prompt"]
    s["scenes"] = sessions.scenes_from_timeline(timeline)
    return serialize_session(sessions.save(s))


# --- scenes -----------------------------------------------------------------
@app.post("/api/sessions/{sid}/scenes")
def add_scene(sid: str, body: dict = Body(default={})):
    s = sessions.require(sid)
    extra = {k: v for k, v in body.items() if k not in ("type", "prompt", "seconds")}
    sc = sessions.new_scene(body.get("type", "text"), body.get("prompt", ""),
                            float(body.get("seconds", 3.0)), **extra)
    s["scenes"].append(sc)
    sessions.save(s)
    return serialize_session(s)


@app.put("/api/sessions/{sid}/scenes/{scene_id}")
def update_scene(sid: str, scene_id: str, patch: dict = Body(...)):
    s = sessions.require(sid)
    sc = next((x for x in s["scenes"] if x["id"] == scene_id), None)
    if not sc:
        raise HTTPException(404, "scene not found")
    sc.update({k: v for k, v in patch.items() if k != "id"})
    return serialize_session(sessions.save(s))


@app.delete("/api/sessions/{sid}/scenes/{scene_id}")
def delete_scene(sid: str, scene_id: str):
    s = sessions.require(sid)
    s["scenes"] = [x for x in s["scenes"] if x["id"] != scene_id]
    return serialize_session(sessions.save(s))


@app.post("/api/sessions/{sid}/scenes/reorder")
def reorder_scenes(sid: str, body: dict = Body(...)):
    s = sessions.require(sid)
    order = body.get("order", [])
    by_id = {x["id"]: x for x in s["scenes"]}
    s["scenes"] = [by_id[i] for i in order if i in by_id] + \
                  [x for x in s["scenes"] if x["id"] not in set(order)]
    return serialize_session(sessions.save(s))


@app.post("/api/sessions/{sid}/upload")
async def upload_asset(sid: str, file: UploadFile = File(...)):
    sessions.require(sid)
    dest = sessions.session_asset_dir(sid) / file.filename
    with open(dest, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    return {"path": str(dest), "url": media_url(str(dest))}


# --- generation jobs --------------------------------------------------------
@app.post("/api/sessions/{sid}/scenes/{scene_id}/image")
def gen_scene_image(sid: str, scene_id: str):
    job = jobs.submit("scene_image", jobs.render_scene_image(sid, scene_id),
                      {"session": sid, "scene": scene_id})
    return job.to_dict()


@app.post("/api/sessions/{sid}/render")
def render(sid: str):
    job = jobs.submit("render", jobs.render_session(sid), {"session": sid})
    return job.to_dict()


class AutoDirect(BaseModel):
    premise: str
    title: str = "Untitled"
    render: bool = False


@app.post("/api/auto-direct")
def auto_direct_endpoint(body: AutoDirect):
    """One-click: make a whole micro-drama from a premise (story -> timeline ->
    stills + voices -> optional render), running as a background job."""
    s = sessions.create(body.title, body.premise)
    job = jobs.submit("auto", jobs.auto_direct(s["id"], body.render), {"session": s["id"]})
    return {"session": serialize_session(s), "job": job.to_dict()}


@app.post("/api/sessions/{sid}/animatic")
def animatic(sid: str, body: dict = Body(default={})):
    """Cheap preview prep: synthesize missing dialogue (+ optionally stills)."""
    sessions.require(sid)
    job = jobs.submit("animatic", jobs.prepare_animatic(sid, bool(body.get("images", False))),
                      {"session": sid})
    return job.to_dict()


@app.post("/api/sessions/{sid}/render/interrupt")
def interrupt_render(sid: str):
    from ..comfy import ComfyClient
    ComfyClient().interrupt()
    return {"ok": True}


# --- gallery: every still/render ever produced for a session ----------------
_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}


@app.get("/api/sessions/{sid}/gallery")
def gallery(sid: str):
    """Scan the session's assets for all stills (grouped per scene) and all
    rendered videos — including previous ones that were superseded."""
    s = sessions.require(sid)
    adir = sessions.session_asset_dir(sid).resolve()
    files = [p for p in adir.iterdir() if p.is_file()]

    def entry(p: Path, current_path) -> dict:
        return {"name": p.name, "url": media_url(str(p)), "mtime": p.stat().st_mtime,
                "is_current": current_path is not None and p.resolve() == current_path}

    cur_video = Path(s["video"]).resolve() if s.get("video") else None
    renders = sorted((p for p in files if p.name.startswith("final_") and p.suffix.lower() == ".mp4"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    render_list = [entry(p, cur_video) for p in renders]

    scene_list = []
    for sc in s.get("scenes", []):
        pre1, pre2 = f"scene_{sc['id']}_", f"upload_{sc['id']}_"
        stills = [p for p in files if p.suffix.lower() in _IMG_EXT
                  and (p.name.startswith(pre1) or p.name.startswith(pre2))]
        stills.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        cur_img = Path(sc["image"]).resolve() if sc.get("image") else None
        scene_list.append({
            "id": sc["id"], "prompt": sc.get("prompt", ""),
            "current_image_url": media_url(sc.get("image")),
            "stills": [entry(p, cur_img) for p in stills],
        })
    return {"renders": render_list, "scenes": scene_list}


def _asset_in_session(sid: str, name: str) -> Path:
    adir = sessions.session_asset_dir(sid).resolve()
    p = (adir / name).resolve()
    if not (p.is_file() and p.parent == adir):
        raise HTTPException(400, "asset not found in this session")
    return p


@app.post("/api/sessions/{sid}/scenes/{scene_id}/select-image")
def select_scene_image(sid: str, scene_id: str, body: dict = Body(...)):
    s = sessions.require(sid)
    sc = next((x for x in s["scenes"] if x["id"] == scene_id), None)
    if not sc:
        raise HTTPException(404, "scene not found")
    sc["image"] = str(_asset_in_session(sid, body.get("name", "")))
    sc["type"] = "image"
    return serialize_session(sessions.save(s))


@app.post("/api/sessions/{sid}/select-render")
def select_render(sid: str, body: dict = Body(...)):
    s = sessions.require(sid)
    s["video"] = str(_asset_in_session(sid, body.get("name", "")))
    return serialize_session(sessions.save(s))


@app.post("/api/tts/preview")
def tts_preview(body: dict = Body(...)):
    text = body.get("text", "")
    voice = body.get("voice", "female, warm tone, clear articulation")
    if not text:
        raise HTTPException(400, "text required")

    def fn(job: jobs.Job):
        from ..tts.tts import tts_line
        out = tts_line(text, voice=voice)
        return {"audio": str(out), "url": media_url(str(out))}
    return jobs.submit("tts_preview", fn, {"text": text}).to_dict()


# --- characters (create / edit / generate + reroll image & voice) -----------
def serialize_character(c: dict) -> dict:
    c = dict(c)
    c["image_url"] = media_url(c.get("image"))
    c["voice_url"] = media_url(c.get("voice_sample"))
    return c


class CharacterIn(BaseModel):
    name: str
    description: str = ""
    look_prompt: str = ""
    voice: str = ""
    sample_text: str = ""


@app.get("/api/characters")
def list_characters():
    return [serialize_character(c) for c in presets.load("characters")]


@app.post("/api/characters/random")
def random_character(body: dict = Body(default={})):
    """LLM-invented character fields for the casting form (not persisted)."""
    return get_director().random_character(body.get("hint", ""))


@app.post("/api/characters")
def create_character(body: CharacterIn):
    return serialize_character(presets.add("characters", body.model_dump()))


@app.put("/api/characters/{cid}")
def edit_character(cid: str, patch: dict = Body(...)):
    res = presets.update("characters", cid, patch)
    if res is None:
        raise HTTPException(404, "character not found")
    return serialize_character(res)


@app.delete("/api/characters/{cid}")
def remove_character(cid: str):
    return {"deleted": presets.delete("characters", cid)}


@app.post("/api/characters/{cid}/image")
def character_image(cid: str):
    if not presets.get("characters", cid):
        raise HTTPException(404, "character not found")
    return jobs.submit("character_image", jobs.render_character_image(cid), {"character": cid}).to_dict()


@app.post("/api/characters/{cid}/voice")
def character_voice(cid: str):
    if not presets.get("characters", cid):
        raise HTTPException(404, "character not found")
    return jobs.submit("character_voice", jobs.render_character_voice(cid), {"character": cid}).to_dict()


@app.post("/api/characters/{cid}/upload-image")
async def upload_character_image(cid: str, file: UploadFile = File(...)):
    if not presets.get("characters", cid):
        raise HTTPException(404, "character not found")
    dest = _save_upload(file, config.CHAR_ASSETS_DIR / f"{cid}_{file.filename}")
    return serialize_character(presets.update("characters", cid, {"image": str(dest)}))


@app.post("/api/characters/{cid}/upload-voice")
async def upload_character_voice(cid: str, file: UploadFile = File(...)):
    """Uploaded clip becomes the character's playable sample AND a voice-clone
    reference OmniVoice uses for that character's dialogue."""
    if not presets.get("characters", cid):
        raise HTTPException(404, "character not found")
    dest = _save_upload(file, config.CHAR_ASSETS_DIR / f"{cid}_voice_{file.filename}")
    return serialize_character(presets.update(
        "characters", cid, {"voice_sample": str(dest), "ref_audio": str(dest)}))


# --- image-conditioned scene script -----------------------------------------
@app.post("/api/sessions/{sid}/scenes/{scene_id}/script")
def scene_script(sid: str, scene_id: str, body: dict = Body(default={})):
    s = sessions.require(sid)
    sc = next((x for x in s["scenes"] if x["id"] == scene_id), None)
    if not sc:
        raise HTTPException(404, "scene not found")
    text = get_director().scene_script(
        sc.get("image"), body.get("concept", ""), body.get("dialogue", ""))
    sc["script"] = text
    if body.get("use_as_prompt", True):
        sc["prompt"] = text
    sessions.save(s)
    return {"script": text, "session": serialize_session(s)}


@app.post("/api/sessions/{sid}/scenes/{scene_id}/upload")
async def upload_scene_image(sid: str, scene_id: str, file: UploadFile = File(...)):
    s = sessions.require(sid)
    sc = next((x for x in s["scenes"] if x["id"] == scene_id), None)
    if not sc:
        raise HTTPException(404, "scene not found")
    dest = _save_upload(file, sessions.session_asset_dir(sid) / f"upload_{scene_id}_{file.filename}")
    sc["image"] = str(dest)
    sc["type"] = "image"
    sessions.save(s)
    return serialize_session(s)


@app.post("/api/sessions/{sid}/music")
async def upload_music(sid: str, file: UploadFile = File(...)):
    """Upload a session-wide soundtrack track, mixed under the whole timeline."""
    s = sessions.require(sid)
    dest = _save_upload(file, sessions.session_asset_dir(sid) / f"music_{file.filename}")
    s["music"] = str(dest)
    return serialize_session(sessions.save(s))


@app.post("/api/sessions/{sid}/scenes/{scene_id}/sfx")
async def upload_scene_sfx(sid: str, scene_id: str, file: UploadFile = File(...)):
    """Upload an SFX/music clip for a single shot, placed at that shot's start."""
    s = sessions.require(sid)
    sc = next((x for x in s["scenes"] if x["id"] == scene_id), None)
    if not sc:
        raise HTTPException(404, "scene not found")
    dest = _save_upload(file, sessions.session_asset_dir(sid) / f"sfx_{scene_id}_{file.filename}")
    sc["sfx"] = str(dest)
    return serialize_session(sessions.save(s))


@app.get("/api/jobs")
def list_jobs():
    return jobs.list_jobs()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    return j


@app.post("/api/jobs/{job_id}/interrupt")
def interrupt_job(job_id: str):
    from ..comfy import ComfyClient
    ComfyClient().interrupt()
    return {"ok": True}
