"""OmniVoice TTS worker — runs as a short-lived subprocess in the project env.

Loads the vendored OmniVoice pipeline (no Wan2GP runtime), synthesizes every
line in a job file to a WAV, then exits so its VRAM is fully released before the
big LTX model loads. Invoked by ``tts.py`` but also runnable directly:

    python -m microdrama.tts.worker --job job.json
    python -m microdrama.tts.worker --text "Hello [laughter]" --out out.wav

Job JSON schema:
    {
      "weights_dir": "<abs path containing omnivoice_*.safetensors + omnivoice/>",
      "extra_ckpt_dirs": ["<optional extra search dirs>"],
      "main_weights": "omnivoice_bf16.safetensors",
      "device": "cuda", "dtype": "bfloat16",
      "lines": [{"text","out_path","audio_prompt_type","alt_prompt","language",
                 "steps","guidance","temperature","pause_seconds",
                 "duration_seconds","seed","ref_audio","ref_audio2"}]
    }
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_VENDOR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))  # makes `omnivoice` and `shared` importable

_DTYPES = {"bfloat16": "bfloat16", "float16": "float16", "float32": "float32"}

# OmniVoice voice-design accepts only this fixed English tag vocabulary; anything
# else raises. We keep the valid subset of whatever voice string we're given and
# fall back to auto-voice ("") so any director/user input synthesizes safely.
VALID_VOICE_TAGS_EN = {
    "american accent", "australian accent", "british accent", "canadian accent",
    "child", "chinese accent", "elderly", "female", "high pitch", "indian accent",
    "japanese accent", "korean accent", "low pitch", "male", "middle-aged",
    "moderate pitch", "portuguese accent", "russian accent", "teenager",
    "very high pitch", "very low pitch", "whisper", "young adult",
}


def _sanitize_voice(alt_prompt: str) -> str:
    kept, seen = [], set()
    for raw in (alt_prompt or "").split(","):
        t = raw.strip().lower()
        if t in VALID_VOICE_TAGS_EN and t not in seen:
            seen.add(t)
            kept.append(t)
    return ", ".join(kept)


def _log(msg: str) -> None:
    print(msg, flush=True)


def load_pipeline(weights_dir: str, main_weights: str, *, device: str = "cuda",
                  dtype: str = "bfloat16", extra_ckpt_dirs: list[str] | None = None):
    import torch
    from shared.utils import files_locator as fl
    from omnivoice.pipeline import OmniVoicePipeline

    search = [weights_dir, *(extra_ckpt_dirs or [])]
    fl.set_checkpoints_paths(search)
    weights_path = fl.locate_file(main_weights)

    torch_dtype = getattr(torch, _DTYPES.get(dtype, "bfloat16"))
    dev = torch.device(device if torch.cuda.is_available() else "cpu")
    _log(f"[worker] loading OmniVoice ({main_weights}) on {dev} / {torch_dtype} ...")

    pipe = OmniVoicePipeline(
        model_weights_path=weights_path,
        ckpt_root=weights_dir,
        device=dev,
        dtype=torch_dtype,
    )
    # mmgp's offloadobj normally streams layers; without it we place the model
    # ourselves (the TTS model + tokenizer fit comfortably in 8GB).
    try:
        pipe.model.to(dev)
        pipe.audio_tokenizer.to(dev)
    except Exception as exc:  # pragma: no cover - fallback to CPU on OOM
        _log(f"[worker] GPU placement failed ({exc}); running on CPU")
        dev = torch.device("cpu")
        pipe.model.to(dev)
        pipe.audio_tokenizer.to(dev)
    pipe.device = dev
    return pipe


def _ensure_whisper(pipe) -> None:
    """Lazy-load Whisper-medium (only needed for voice-cloning reference audio)."""
    if getattr(pipe, "_whisper_model", None) is not None:
        return
    import whisper
    _log("[worker] loading Whisper-medium for reference transcription ...")
    pipe.set_whisper_model(whisper.load_model("medium", device="cpu"))


def _save_wav(result: dict, out_path: str) -> None:
    import numpy as np
    import soundfile as sf
    import torch

    audio = result["x"]
    sr = int(result["audio_sampling_rate"])
    if isinstance(audio, torch.Tensor):
        audio = audio.detach().to(torch.float32).cpu().numpy()
    audio = np.asarray(audio, dtype=np.float32).squeeze()
    if audio.ndim == 2 and audio.shape[0] <= 2:  # (channels, samples) -> (samples, channels)
        audio = audio.T
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, audio, sr)


def synthesize_line(pipe, line: dict) -> str:
    apt = (line.get("audio_prompt_type") or "").upper()
    if "A" in apt and not line.get("ref_text"):
        _ensure_whisper(pipe)

    # In voice-design mode the alt_prompt must be valid voice tags; for cloning
    # ("A"/"AB") it is a reference transcript and is passed through untouched.
    raw_alt = line.get("alt_prompt", "")
    alt_prompt = raw_alt if "A" in apt else _sanitize_voice(raw_alt)

    result = pipe.generate(
        input_prompt=line["text"],
        model_mode=line.get("language", "auto"),
        audio_guide=line.get("ref_audio"),
        audio_guide2=line.get("ref_audio2"),
        alt_prompt=alt_prompt,
        audio_prompt_type=line.get("audio_prompt_type", ""),
        sampling_steps=int(line.get("steps", 32)),
        guide_scale=float(line.get("guidance", 2.0)),
        temperature=float(line.get("temperature", 0.1)),
        pause_seconds=float(line.get("pause_seconds", 0.2)),
        duration_seconds=(line.get("duration_seconds") or None),
        seed=int(line.get("seed", -1)),
    )
    if not result or "x" not in result:
        raise RuntimeError(f"OmniVoice returned no audio for: {line['text'][:60]!r}")
    _save_wav(result, line["out_path"])
    return line["out_path"]


def run_job(job: dict) -> list[str]:
    pipe = load_pipeline(
        job["weights_dir"], job.get("main_weights", "omnivoice_bf16.safetensors"),
        device=job.get("device", "cuda"), dtype=job.get("dtype", "bfloat16"),
        extra_ckpt_dirs=job.get("extra_ckpt_dirs"),
    )
    out = []
    lines = job["lines"]
    for i, line in enumerate(lines):
        _log(f"[worker] ({i + 1}/{len(lines)}) synthesizing -> {line['out_path']}")
        out.append(synthesize_line(pipe, line))
    _log("[worker] done")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job", help="Path to a job JSON file")
    ap.add_argument("--text", help="Quick single-line synth (debug)")
    ap.add_argument("--out", help="Output wav path for --text")
    ap.add_argument("--weights-dir", help="Weights dir for --text mode")
    ap.add_argument("--alt-prompt", default="female, warm tone, clear articulation")
    args = ap.parse_args()

    if args.job:
        job = json.loads(Path(args.job).read_text(encoding="utf-8"))
    elif args.text and args.out and args.weights_dir:
        job = {
            "weights_dir": args.weights_dir,
            "lines": [{"text": args.text, "out_path": args.out,
                       "alt_prompt": args.alt_prompt, "language": "auto"}],
        }
    else:
        ap.error("provide --job, or --text + --out + --weights-dir")

    run_job(job)


if __name__ == "__main__":
    main()
