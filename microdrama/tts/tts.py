"""Backend-facing OmniVoice helper.

Runs synthesis in a short-lived subprocess (``microdrama.tts.worker``) so the
TTS model's VRAM is released before the LTX render; frees ComfyUI's models
first so the two never fight over the 8GB GPU. Also handles one-time weight
download from Hugging Face into the project's models dir.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from .. import config


def weights_present(main_weights: str | None = None) -> bool:
    main = main_weights or config.TTS_MAIN_WEIGHTS
    search = [config.TTS_WEIGHTS_DIR, *map(Path, config.TTS_EXTRA_CKPT_DIRS)]
    return any((d / main).exists() and (d / "omnivoice" / "config.json").exists()
               for d in search)


def download_weights(main_weights: str | None = None) -> Path:
    """Download OmniVoice assets from HF into models/tts/ (idempotent)."""
    from huggingface_hub import snapshot_download

    main = main_weights or config.TTS_MAIN_WEIGHTS
    config.TTS_WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=config.TTS_REPO,
        local_dir=str(config.TTS_WEIGHTS_DIR),
        allow_patterns=[main, "omnivoice/*", "omnivoice/**"],
    )
    return config.TTS_WEIGHTS_DIR / main


def synthesize(
    lines: list[dict],
    *,
    device: str | None = None,
    dtype: str | None = None,
    main_weights: str | None = None,
    free_comfy: bool = True,
    auto_download: bool = True,
) -> list[Path]:
    """Synthesize a batch of lines to WAVs. Each line may set ``out_path``;
    otherwise one is assigned under outputs/audio. Returns the WAV paths.

    Line keys: text (required), alt_prompt, audio_prompt_type ("" | "A" | "AB"),
    language, steps, guidance, temperature, pause_seconds, duration_seconds,
    seed, ref_audio, ref_audio2, ref_text, out_path.
    """
    config.ensure_dirs()
    main = main_weights or config.TTS_MAIN_WEIGHTS
    if auto_download and not weights_present(main):
        download_weights(main)

    prepared = []
    for line in lines:
        line = dict(line)
        if not line.get("text"):
            raise ValueError("each TTS line needs non-empty 'text'")
        line.setdefault("out_path", str(config.AUDIO_DIR / f"tts_{uuid.uuid4().hex[:10]}.wav"))
        prepared.append(line)

    job = {
        "weights_dir": str(config.TTS_WEIGHTS_DIR),
        "extra_ckpt_dirs": config.TTS_EXTRA_CKPT_DIRS,
        "main_weights": main,
        "device": device or config.TTS_DEVICE,
        "dtype": dtype or config.TTS_DTYPE,
        "lines": prepared,
    }

    if free_comfy:
        # Release ComfyUI's models so OmniVoice has the GPU to itself.
        from ..comfy.client import ComfyClient
        ComfyClient().free()

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
        json.dump(job, fh)
        job_path = fh.name

    cmd = [sys.executable, "-m", "microdrama.tts.worker", "--job", job_path]
    subprocess.run(cmd, cwd=str(config.PROJECT_ROOT), check=True)
    return [Path(line["out_path"]) for line in prepared]


def tts_line(text: str, *, voice: str = "female, warm tone, clear articulation",
             out_path: str | Path | None = None, **kw) -> Path:
    """Convenience: synthesize a single voice-design line."""
    line = {"text": text, "alt_prompt": voice, "audio_prompt_type": "",
            "language": kw.pop("language", "auto"), **kw}
    if out_path:
        line["out_path"] = str(out_path)
    return synthesize([line])[0]
