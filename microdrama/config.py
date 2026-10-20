"""Central configuration for the AI Microdrama Studio.

All paths are resolved relative to the project root so the whole project stays
self-contained. Anything here can be overridden with an environment variable of
the same name (see ``_env``).
"""
from __future__ import annotations

import os
from pathlib import Path

# --- Project layout -------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = PROJECT_ROOT / "workflows"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
IMAGES_DIR = OUTPUTS_DIR / "images"
EDITS_DIR = OUTPUTS_DIR / "edits"
AUDIO_DIR = OUTPUTS_DIR / "audio"
VIDEOS_DIR = OUTPUTS_DIR / "videos"
SESSIONS_DIR = OUTPUTS_DIR / "sessions"
CHAR_ASSETS_DIR = OUTPUTS_DIR / "characters"
PRESETS_DIR = PROJECT_ROOT / "presets"
MODELS_DIR = PROJECT_ROOT / "models"
TTS_WEIGHTS_DIR = MODELS_DIR / "tts"


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


# --- External services ----------------------------------------------------
COMFY_URL = _env("COMFY_URL", "http://localhost:8188").rstrip("/")

# OpenAI-compatible "director" LLM. NOTE: port 3000 (not 3001); /v1/models is
# not implemented on this server, so only chat/completions is used.
LLM_BASE_URL = _env("LLM_BASE_URL", "http://localhost:3000/v1").rstrip("/")
LLM_MODEL = _env("LLM_MODEL", "gpt-5-mini")
LLM_API_KEY = _env("LLM_API_KEY", "not-needed")  # local server ignores it

# --- ComfyUI install (for input uploads + auto-start) ---------------------
COMFY_ROOT = Path(_env("COMFY_ROOT", r"C:\Users\micke\Desktop\AI\ComfyUI"))
COMFY_INPUT_DIR = COMFY_ROOT / "input"
COMFY_START_BAT = COMFY_ROOT / "start.bat"

# --- Wan2GP (source + weights may be reused; its ENV must NOT be used) -----
WAN2GP_ROOT = Path(_env("WAN2GP_ROOT", r"C:\Users\micke\Desktop\AI\Wan2GP"))
WAN2GP_CKPTS = WAN2GP_ROOT / "ckpts"

# --- Default model filenames per workflow (overridable per call) ----------
ZIMAGE_MODELS = {
    "unet": "z_image_turbo_bf16.safetensors",
    "vae": "ae.safetensors",
    "clip": "qwen_3_4b_fp4_mixed.safetensors",
}
FLUX_MODELS = {
    "unet": "flux-2-klein-9b-fp8.safetensors",
    "vae": "flux2-vae.safetensors",
    "clip": "qwen_3_8b_fp4mixed.safetensors",
}

# --- OmniVoice TTS (ported into this project's env) -----------------------
TTS_REPO = _env("TTS_REPO", "DeepBeepMeep/TTS")
TTS_MAIN_WEIGHTS = _env("TTS_MAIN_WEIGHTS", "omnivoice_bf16.safetensors")
TTS_DEVICE = _env("TTS_DEVICE", "cuda")
TTS_DTYPE = _env("TTS_DTYPE", "bfloat16")

# Cap total LTX render length so default dramas stay feasible on an 8GB GPU.
# Raise MAX_RENDER_FRAMES for longer videos (slower / higher VRAM).
MAX_RENDER_FRAMES = int(_env("MAX_RENDER_FRAMES", "145"))
# Extra dirs to search for already-downloaded weights (Wan2GP ckpts may be reused).
TTS_EXTRA_CKPT_DIRS = [str(WAN2GP_CKPTS)] if WAN2GP_CKPTS.exists() else []

# Default negative prompt reused across image workflows.
DEFAULT_IMAGE_NEGATIVE = (
    "blurry, low resolution, distorted face, extra limbs, unrealistic body "
    "proportions, poor lighting, dull colors, overexposed, underexposed, messy "
    "background, text, watermark, logo, cartoon style, overly stylized, harsh "
    "shadows, noise"
)


def ensure_dirs() -> None:
    """Create all output directories (idempotent)."""
    for d in (
        IMAGES_DIR, EDITS_DIR, AUDIO_DIR, VIDEOS_DIR, SESSIONS_DIR,
        CHAR_ASSETS_DIR, PRESETS_DIR, TTS_WEIGHTS_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
