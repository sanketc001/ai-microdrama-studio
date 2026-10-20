"""Background job queue + the finalize/render pipeline.

One global GPU lock serializes every heavy step (image gen, TTS, LTX) so the
8GB card is never double-booked. Jobs run on worker threads; the API polls
their status. The headline job, ``render_session``, chains:
guide images -> dialogue TTS (frees ComfyUI first) -> single LTX render.
"""
from __future__ import annotations

import io
import threading
import time
import traceback
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable

from .. import config
from ..comfy import ComfyClient, edit_image, generate_image, generate_microdrama
from ..director import DirectorLLM
from ..presets import store as presets
from . import sessions

GPU_LOCK = threading.Lock()
JOBS: dict[str, "Job"] = {}


class Job:
    def __init__(self, kind: str, meta: dict | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.meta = meta or {}
        self.status = "queued"      # queued -> running -> done | error
        self.progress: dict = {}
        self.preview: str | None = None   # live sampling-preview frame URL
        self.logs: list[str] = []
        self.result: Any = None
        self.error: str | None = None
        self.created = time.time()

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "meta": self.meta,
            "status": self.status, "progress": self.progress, "preview": self.preview,
            "logs": self.logs[-50:], "result": self.result, "error": self.error,
        }

    def summary(self) -> dict:
        """Lightweight view for the global renders monitor (no full logs)."""
        return {
            "id": self.id, "kind": self.kind, "status": self.status,
            "progress": self.progress, "preview": self.preview,
            "meta": self.meta, "created": self.created,
            "log": self.logs[-1] if self.logs else "",
            "error": bool(self.error),
        }

    def log(self, msg: str) -> None:
        self.logs.append(msg)

    def progress_cb(self, stage: str) -> Callable[[dict], None]:
        def cb(msg: dict):
            t, d = msg.get("type"), msg.get("data", {})
            if t == "progress":
                v, m = d.get("value", 0), d.get("max", 1)
                self.progress = {"stage": stage, "value": v, "max": m,
                                 "pct": int(100 * v / max(1, m))}
            elif t == "executing" and d.get("node"):
                self.progress = {"stage": stage, "node": d["node"]}
        return cb


def get(job_id: str) -> dict | None:
    j = JOBS.get(job_id)
    return j.to_dict() if j else None


def list_jobs(limit: int = 40) -> list[dict]:
    """Most-recent jobs first (summaries), for the global renders monitor."""
    ordered = sorted(JOBS.values(), key=lambda j: j.created, reverse=True)
    return [j.summary() for j in ordered[:limit]]


def submit(kind: str, fn: Callable[["Job"], Any], meta: dict | None = None) -> Job:
    """Run ``fn(job)`` on a worker thread, serialized by the GPU lock."""
    job = Job(kind, meta)
    JOBS[job.id] = job

    def runner():
        with GPU_LOCK:
            job.status = "running"
            try:
                job.result = fn(job)
                job.status = "done"
            except Exception as exc:  # noqa: BLE001
                job.error = f"{exc}\n{traceback.format_exc()}"
                job.status = "error"
    threading.Thread(target=runner, daemon=True).start()
    return job


# --- character helpers ------------------------------------------------------
def character_refs(scene: dict) -> list[str]:
    """Portrait image paths for characters that start (appear in) this scene."""
    refs = []
    for cid in scene.get("character_ids") or []:
        c = presets.get("characters", cid)
        if c and c.get("image") and Path(c["image"]).exists():
            refs.append(c["image"])
    return refs


def guide_image(scene: dict, session: dict, *, client, out_dir, prefix, on_progress):
    """Generate a scene's guide still. If characters start the scene and have
    portraits, composite them in (Flux multi-reference) for visual consistency;
    otherwise plain text-to-image."""
    prompt = (scene.get("image_prompt") or scene.get("prompt")
              or session.get("global_prompt") or "cinematic scene")
    refs = character_refs(scene)
    if refs:
        return edit_image(refs, prompt, filename_prefix=prefix, out_dir=out_dir,
                          client=client, on_progress=on_progress)
    return generate_image(prompt, filename_prefix=prefix, out_dir=out_dir,
                          client=client, on_progress=on_progress)


def prepare_assets(session: dict, job: "Job", *, want_images: bool = True,
                   want_audio: bool = True, client=None) -> dict:
    """Ensure scenes have guide stills (optional) and per-scene dialogue audio.
    Shared by the full render and the animatic preview; idempotent (skips assets
    that already exist). Mutates + saves the session."""
    sid = session["id"]
    scenes = session.get("scenes") or []
    asset_dir = sessions.session_asset_dir(sid)
    client = client or ComfyClient()

    if want_images:
        for sc in scenes:
            if sc.get("type") == "image" and not sc.get("image") and (
                    sc.get("image_prompt") or character_refs(sc)):
                job.log(f"Guide image: {sc['id']}")
                out = guide_image(sc, session, client=client, out_dir=asset_dir,
                                  prefix=f"sessions/{sid}/scene_{sc['id']}",
                                  on_progress=job.progress_cb("image"))
                sc["image"] = str(out[0]) if out else None
        sessions.save(session)

    if want_audio:
        tts_lines, scene_audio = [], {}
        for sc in scenes:
            dlg = sc.get("dialogue") or []
            text = "\n".join(d.get("text", "") for d in dlg if d.get("text"))
            if not text.strip() or sc.get("audio"):
                continue
            out_path = str(asset_dir / f"audio_{sc['id']}.wav")
            line = {"text": text, "language": dlg[0].get("language", "auto"), "out_path": out_path}
            # If a character in this shot has an uploaded voice clip, clone it.
            ref = None
            for cid in sc.get("character_ids", []) or []:
                c = presets.get("characters", cid)
                if c and c.get("ref_audio") and Path(c["ref_audio"]).exists():
                    ref = c["ref_audio"]
                    break
            if ref:
                line.update(audio_prompt_type="A", ref_audio=ref)
            else:
                line.update(audio_prompt_type="", alt_prompt=dlg[0].get("voice", "neutral, clear"))
            tts_lines.append(line)
            scene_audio[sc["id"]] = out_path
        if tts_lines:
            job.log(f"Synthesizing {len(tts_lines)} dialogue track(s) with OmniVoice")
            from ..tts.tts import synthesize
            synthesize(tts_lines)  # frees ComfyUI's models first
            for sc in scenes:
                if sc["id"] in scene_audio:
                    sc["audio"] = scene_audio[sc["id"]]
            sessions.save(session)
    return session


# --- job implementations ---------------------------------------------------
def prepare_animatic(session_id: str, want_images: bool = False) -> Callable[[Job], Any]:
    """Cheap preview prep: synthesize any missing per-scene dialogue (and
    optionally missing stills) so the animatic has real voices — no LTX render."""
    def fn(job: Job):
        s = sessions.require(session_id)
        prepare_assets(s, job, want_images=want_images, want_audio=True)
        return {"ok": True, "scenes": len(s.get("scenes") or [])}
    return fn
def render_character_image(char_id: str) -> Callable[[Job], Any]:
    def fn(job: Job):
        c = presets.get("characters", char_id)
        if not c:
            raise KeyError(f"character {char_id} not found")
        prompt = c.get("look_prompt") or c.get("description") or c.get("name") or "portrait"
        job.log(f"Rendering portrait for {c.get('name')}")
        out = generate_image(prompt, width=768, height=768,
                             filename_prefix=f"presets/characters/{char_id}",
                             on_progress=job.progress_cb("image"))
        img = str(out[0]) if out else None
        presets.update("characters", char_id, {"image": img})
        return {"image": img}
    return fn


def render_character_voice(char_id: str) -> Callable[[Job], Any]:
    def fn(job: Job):
        c = presets.get("characters", char_id)
        if not c:
            raise KeyError(f"character {char_id} not found")
        text = c.get("sample_text") or f"Hi, I'm {c.get('name', 'your character')}. This is how I sound."
        out_path = str(config.AUDIO_DIR / f"voice_{char_id}.wav")
        job.log(f"Synthesizing voice for {c.get('name')}")
        from ..tts.tts import synthesize
        synthesize([{"text": text, "alt_prompt": c.get("voice", ""),
                     "audio_prompt_type": "", "out_path": out_path}])
        presets.update("characters", char_id, {"voice_sample": out_path})
        return {"voice_sample": out_path}
    return fn


def render_scene_image(session_id: str, scene_id: str) -> Callable[[Job], Any]:
    def fn(job: Job):
        s = sessions.require(session_id)
        sc = next((x for x in s["scenes"] if x["id"] == scene_id), None)
        if not sc:
            raise KeyError(f"scene {scene_id} not found")
        job.log(f"Generating guide image for scene {scene_id}")
        out = guide_image(sc, s, client=ComfyClient(),
                          out_dir=sessions.session_asset_dir(session_id),
                          prefix=f"sessions/{session_id}/scene_{scene_id}",
                          on_progress=job.progress_cb("image"))
        sc["image"] = str(out[0]) if out else None
        sc["type"] = "image"
        sessions.save(s)
        return {"image": sc["image"]}
    return fn


def _render_video(s: dict, job: "Job", client=None) -> str | None:
    """Assemble the LTX timeline from an already-prepared session (stills+audio)
    and render the video, with a live looping-GIF preview. Mixes per-shot
    dialogue + SFX and the session music track onto the timeline."""
    client = client or ComfyClient()
    sid = s["id"]
    fr = int(s.get("frame_rate", 24))
    scenes = s.get("scenes") or []
    asset_dir = sessions.session_asset_dir(sid)

    # cap total length so a render stays feasible on a small GPU
    raw_lengths = [max(1, round(float(sc.get("seconds", 3.0)) * fr)) for sc in scenes]
    total = sum(raw_lengths)
    cap = config.MAX_RENDER_FRAMES
    if total > cap:
        scale = cap / total
        lengths = [max(8, round(n * scale)) for n in raw_lengths]
        job.log(f"Capped render to ~{cap} frames (from {total}) for GPU memory")
    else:
        lengths = raw_lengths

    segments, audio_list, pos = [], [], 0
    for sc, length in zip(scenes, lengths):
        seg_type = sc.get("type", "text")
        if seg_type == "image" and not sc.get("image"):
            seg_type = "text"  # fall back if the still is missing
        seg = {"type": seg_type, "length_frames": length,
               "prompt": sc.get("prompt") or s.get("global_prompt") or "cinematic scene"}
        if seg_type == "image":
            seg["image_path"] = sc["image"]
            seg["guide_strength"] = float(sc.get("guide_strength", 1.0))
        segments.append(seg)
        if sc.get("audio"):
            audio_list.append({"audio_path": sc["audio"], "start": pos, "length": length})
        if sc.get("sfx"):
            audio_list.append({"audio_path": sc["sfx"], "start": pos, "length": length})
        pos += length
    if s.get("music"):  # session-wide soundtrack under the whole timeline
        audio_list.append({"audio_path": s["music"], "start": 0, "length": pos})

    # live sampling-preview frames -> looping GIF so the UI shows motion building up
    from PIL import Image
    _frames: deque = deque(maxlen=40)
    _last_gif = [0.0]
    gif_path = asset_dir / "_preview.gif"

    def on_preview(frame: bytes):
        try:
            im = Image.open(io.BytesIO(frame)).convert("RGB")
            im.thumbnail((360, 360))
            _frames.append(im)
            now = time.time()
            if now - _last_gif[0] < 1.2 and len(_frames) > 1:
                return
            _last_gif[0] = now
            seq = list(_frames)
            seq[0].save(gif_path, format="GIF", save_all=True, append_images=seq[1:],
                        duration=100, loop=0, optimize=True, disposal=2)
            job.preview = f"/media/sessions/{sid}/assets/_preview.gif?t={int(now * 1000)}"
        except Exception:
            pass

    job.log("Rendering micro-drama with LTX (this can take a while)")
    client.free()
    out = generate_microdrama(
        s.get("global_prompt") or s.get("premise") or "a short cinematic micro-drama",
        segments, audio=audio_list or None, frame_rate=fr,
        out_dir=asset_dir, filename_prefix=f"sessions/{sid}/final",
        client=client, on_progress=job.progress_cb("ltx"), on_preview=on_preview, timeout=3600,
    )
    s["video"] = str(out[0]) if out else None
    sessions.save(s)
    return s["video"]


def render_session(session_id: str) -> Callable[[Job], Any]:
    def fn(job: Job):
        s = sessions.require(session_id)
        if not (s.get("scenes") or []):
            raise ValueError("session has no scenes to render")
        client = ComfyClient()
        prepare_assets(s, job, want_images=True, want_audio=True, client=client)
        _render_video(s, job, client=client)
        return {"video": s.get("video")}
    return fn


def auto_direct(session_id: str, do_render: bool = False) -> Callable[[Job], Any]:
    """One-click: direct a story from the premise, compile the timeline, prepare
    stills + voices, and optionally render — all autonomously."""
    def fn(job: Job):
        s = sessions.require(session_id)
        d = DirectorLLM()
        job.log("Directing the story…")
        s["story"] = d.propose_story(s.get("premise", ""),
                                     characters=presets.load("characters"),
                                     scenes=presets.load("scenes"))
        if (not s.get("title") or s["title"] == "Untitled") and s["story"].get("title"):
            s["title"] = s["story"]["title"]
        sessions.save(s)
        job.log("Compiling the timeline…")
        tl = d.compile_timeline(s["story"])
        if tl.get("global_prompt"):
            s["global_prompt"] = tl["global_prompt"]
        s["scenes"] = sessions.scenes_from_timeline(tl)
        sessions.save(s)
        prepare_assets(s, job, want_images=True, want_audio=True)
        if do_render:
            _render_video(s, job)
        return {"session": session_id, "scenes": len(s.get("scenes") or []), "video": s.get("video")}
    return fn
