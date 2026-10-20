"""Drama-project (session) state, persisted as JSON under outputs/sessions/<id>/.

A session is a global prompt + an ordered list of scenes the user composes
(each scene = one LTX segment: text or image beat, with a prompt, a length, an
optional guide image, and optional dialogue lines), plus the evolving narrative
state from the director and the final rendered video path.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from .. import config


def _dir(session_id: str) -> Path:
    return config.SESSIONS_DIR / session_id


def _file(session_id: str) -> Path:
    return _dir(session_id) / "session.json"


def session_asset_dir(session_id: str) -> Path:
    d = _dir(session_id) / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create(title: str = "Untitled", premise: str = "", frame_rate: int = 24,
           parent_id: str | None = None) -> dict:
    sid = uuid.uuid4().hex[:12]
    now = time.time()
    session = {
        "id": sid,
        "title": title,
        "premise": premise,
        "global_prompt": "",
        "story": {},          # director narrative state (beats, choices, characters)
        "scenes": [],         # composed timeline
        "frame_rate": frame_rate,
        "music": None,        # optional session-wide soundtrack track
        "video": None,
        "parent_id": parent_id,  # set for branches / continuations
        "created": now,
        "updated": now,
    }
    _dir(sid).mkdir(parents=True, exist_ok=True)
    save(session)
    return session


def branch(session_id: str) -> dict:
    """Deep-copy a session as a new take (non-destructive exploration)."""
    import copy
    src = require(session_id)
    s = copy.deepcopy(src)
    s["id"] = uuid.uuid4().hex[:12]
    s["parent_id"] = session_id
    s["title"] = (src.get("title") or "Untitled") + " (branch)"
    s["video"] = None
    s["created"] = s["updated"] = time.time()
    _dir(s["id"]).mkdir(parents=True, exist_ok=True)
    save(s)
    return s


def save(session: dict) -> dict:
    session["updated"] = time.time()
    _dir(session["id"]).mkdir(parents=True, exist_ok=True)
    _file(session["id"]).write_text(json.dumps(session, indent=2, ensure_ascii=False),
                                    encoding="utf-8")
    return session


def get(session_id: str) -> dict | None:
    f = _file(session_id)
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def require(session_id: str) -> dict:
    s = get(session_id)
    if s is None:
        raise KeyError(f"session {session_id} not found")
    return s


def list_sessions() -> list[dict]:
    out = []
    if not config.SESSIONS_DIR.exists():
        return out
    for d in config.SESSIONS_DIR.iterdir():
        f = d / "session.json"
        if f.exists():
            s = json.loads(f.read_text(encoding="utf-8"))
            out.append({k: s.get(k) for k in ("id", "title", "premise", "video", "updated", "parent_id")})
    return sorted(out, key=lambda s: s.get("updated", 0), reverse=True)


def delete(session_id: str) -> bool:
    import shutil
    d = _dir(session_id)
    if not d.exists():
        return False
    shutil.rmtree(d, ignore_errors=True)
    return True


# --- scene helpers ---------------------------------------------------------
def new_scene(type_: str = "text", prompt: str = "", seconds: float = 3.0,
              **extra: Any) -> dict:
    return {
        "id": uuid.uuid4().hex[:8],
        "type": type_,
        "prompt": prompt,
        "seconds": seconds,
        "image_prompt": extra.get("image_prompt", ""),
        "image": extra.get("image"),
        "guide_strength": extra.get("guide_strength", 1.0),
        "dialogue": extra.get("dialogue", []),
        "character_ids": extra.get("character_ids", []),
        "script": extra.get("script", ""),
        "sfx": extra.get("sfx"),
    }


def scenes_from_timeline(timeline: dict) -> list[dict]:
    """Convert a director compile_timeline() result into scene dicts."""
    scenes = []
    for sc in timeline.get("scenes", []):
        scenes.append(new_scene(
            type_=sc.get("type", "text"),
            prompt=sc.get("prompt", ""),
            seconds=float(sc.get("seconds", 3.0)),
            image_prompt=sc.get("image_prompt", ""),
            guide_strength=float(sc.get("guide_strength", 1.0)),
            dialogue=sc.get("dialogue", []),
        ))
    return scenes
