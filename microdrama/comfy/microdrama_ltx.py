"""Render a full micro-drama in one pass via the LTX Director workflow.

Takes a high-level list of scene ``segments`` (text or image beats, each with a
prompt and a length) plus optional custom audio, assembles the LTXDirector
timeline fields, patches the two-pass LTX workflow, and renders a video with
synchronized audio. See the LTXDirector control-surface notes for field rules.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from .. import config
from .client import ComfyClient, ProgressCb, load_workflow
from ._common import rand_seed, run_workflow

_TEMPLATE = "ltx_director.json"


def _normalize_segments(segments: list[dict]) -> list[dict]:
    """Validate and fill defaults (cumulative starts, ints) for each segment."""
    if not segments:
        raise ValueError("generate_microdrama requires at least one segment")
    out, pos = [], 0
    for i, seg in enumerate(segments):
        prompt = (seg.get("prompt") or "").strip()
        if not prompt:
            raise ValueError(
                f"segment {i} is missing a prompt — LTXDirector requires a "
                "non-empty prompt for every segment (text and image)"
            )
        length = int(seg.get("length_frames") or seg.get("length") or 0)
        if length <= 0:
            raise ValueError(f"segment {i} needs a positive length_frames")
        start = int(seg.get("start", pos))
        pos = start + length
        stype = seg.get("type", "text")
        if stype not in ("text", "image"):
            raise ValueError(f"segment {i} type must be 'text' or 'image'")
        if stype == "image" and not seg.get("image_path"):
            raise ValueError(f"segment {i} is type 'image' but has no image_path")
        out.append({
            "type": stype, "prompt": prompt, "start": start, "length": length,
            "image_path": seg.get("image_path"),
            "guide_strength": float(seg.get("guide_strength", 1.0)),
        })
    return out


def generate_microdrama(
    global_prompt: str,
    segments: list[dict],
    *,
    audio: dict | list[dict] | None = None,
    frame_rate: float = 24,
    duration_frames: int | None = None,
    base_seed: int | None = None,
    base_steps: int = 8,
    refine_steps: int = 4,
    refine_denoise: float = 0.42,
    base_scale_by: float = 0.5,
    epsilon: float = 0.001,
    custom_width: int = 0,
    custom_height: int = 0,
    use_custom_audio: bool | None = None,
    filename_prefix: str = "video/LTX_Director",
    out_dir: Path | str = config.VIDEOS_DIR,
    client: ComfyClient | None = None,
    on_progress: ProgressCb | None = None,
    on_preview: Callable[[bytes], None] | None = None,
    timeout: float = 3600.0,
) -> list[Path]:
    """Render a micro-drama from ``global_prompt`` + ``segments`` (+ optional audio).

    ``segments``: list of ``{type:"text"|"image", prompt, length_frames,
    image_path?, guide_strength?, start?}``. ``audio``: one dict or a list of
    ``{audio_path, start?, length?, trim_start?}`` (multiple dialogue/music
    clips can be placed across the timeline). Returns the saved video path(s).
    """
    segs = _normalize_segments(segments)
    client = client or ComfyClient()

    if duration_frames is None:
        duration_frames = max(s["start"] + s["length"] for s in segs)
    duration_seconds = round(duration_frames / float(frame_rate), 3)

    # --- build timeline_data.segments (upload guide images) ---
    tl_segments = []
    for i, s in enumerate(segs):
        node = {"id": f"seg{i}", "start": s["start"], "length": s["length"],
                "prompt": s["prompt"], "type": s["type"]}
        if s["type"] == "image":
            node["imageFile"] = client.upload(s["image_path"])
            node["imageB64"] = ""
        tl_segments.append(node)

    # --- audio segments (optional; dict or list of dicts) ---
    audio_list = [audio] if isinstance(audio, dict) else list(audio or [])
    audio_segments = []
    for j, a in enumerate(audio_list):
        audio_segments.append({
            "id": f"aud{j}", "type": "audio",
            "start": int(a.get("start", 0)),
            "length": int(a.get("length") or duration_frames),
            "trimStart": int(a.get("trim_start", 0)),
            "audioFile": client.upload(a["audio_path"]),
            "fileName": Path(a["audio_path"]).name,
        })
    if use_custom_audio is None:
        use_custom_audio = bool(audio_segments)

    timeline_data = json.dumps({"segments": tl_segments, "audioSegments": audio_segments})
    local_prompts = " | ".join(s["prompt"] for s in segs)
    segment_lengths = ",".join(str(s["length"]) for s in segs)
    img_strengths = [s["guide_strength"] for s in sorted(segs, key=lambda s: s["start"])
                     if s["type"] == "image"]
    guide_strength = ",".join(f"{v:.2f}" for v in img_strengths)

    # --- patch the workflow ---
    g = copy.deepcopy(load_workflow(_TEMPLATE))
    seed = rand_seed() if base_seed is None else base_seed

    g["46"]["inputs"].update(
        global_prompt=global_prompt,
        duration_frames=int(duration_frames),
        duration_seconds=duration_seconds,
        timeline_data=timeline_data,
        local_prompts=local_prompts,
        segment_lengths=segment_lengths,
        guide_strength=guide_strength,
        epsilon=epsilon,
        use_custom_audio=use_custom_audio,
        frame_rate=frame_rate,
        custom_width=custom_width,
        custom_height=custom_height,
    )
    g["28"]["inputs"]["noise_seed"] = seed          # shared by both samplers
    g["11"]["inputs"]["steps"] = base_steps         # base pass
    g["54"]["inputs"]["steps"] = refine_steps       # refine pass
    g["54"]["inputs"]["denoise"] = refine_denoise
    g["8"]["inputs"]["scale_by"] = base_scale_by    # base guide downscale
    g["30"]["inputs"]["filename_prefix"] = filename_prefix

    return run_workflow(g, out_dir, client=client, on_progress=on_progress,
                        on_preview=on_preview, timeout=timeout)
