"""JSON-backed preset library (characters, scenes, voices, dialogues, storylines).

The library is generated once by scripts/generate_presets.py and is then fully
user-editable through the backend. Each kind is a list of dicts saved under
presets/<kind>.json. Everything lives inside the project directory.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .. import config

KINDS = ("characters", "scenes", "voices", "dialogues", "storylines")


def _path(kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown preset kind {kind!r}; expected one of {KINDS}")
    return config.PRESETS_DIR / f"{kind}.json"


def load(kind: str) -> list[dict]:
    p = _path(kind)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def save(kind: str, items: list[dict]) -> None:
    config.PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    _path(kind).write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def all_presets() -> dict[str, list[dict]]:
    return {kind: load(kind) for kind in KINDS}


def get(kind: str, item_id: str) -> dict | None:
    return next((it for it in load(kind) if it.get("id") == item_id), None)


def add(kind: str, item: dict) -> dict:
    item = dict(item)
    item.setdefault("id", uuid.uuid4().hex[:12])
    item.setdefault("custom", True)
    items = load(kind)
    items.append(item)
    save(kind, items)
    return item


def update(kind: str, item_id: str, patch: dict) -> dict | None:
    items = load(kind)
    for it in items:
        if it.get("id") == item_id:
            it.update(patch)
            save(kind, items)
            return it
    return None


def delete(kind: str, item_id: str) -> bool:
    items = load(kind)
    new = [it for it in items if it.get("id") != item_id]
    if len(new) == len(items):
        return False
    save(kind, new)
    return True


def seed_if_empty(items_by_kind: dict[str, list[dict]]) -> None:
    """Write generated presets only for kinds that have no file yet."""
    for kind, items in items_by_kind.items():
        if not _path(kind).exists():
            save(kind, items)
