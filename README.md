# AI Microdrama Studio

A CYOA-style studio for AI-generated **micro-dramas**. Plan a timeline of scenes
— stills, dialogue, and custom voices — with help from an LLM **director** and a
library of presets, then render the whole thing (video **with** synced audio) in
a single LTX-Video pass on a local ComfyUI.

Everything (code, presets, generated media, ported model code) lives inside this
project directory.

## How it works

| Layer | What | Where |
|------|------|-------|
| **Workflows → functions** | The 4 ComfyUI workflows wrapped as plain Python | `microdrama/comfy/` |
| **Director** | `gpt-5-mini` writes the branching story + compiles it into render params | `microdrama/director/` |
| **Voice** | OmniVoice TTS **ported** from Wan2GP (code only) into this env | `microdrama/tts/` |
| **Presets** | Generated library of characters/scenes/voices/dialogues/storylines | `microdrama/presets/`, `presets/` |
| **Backend** | FastAPI: sessions, scenes, jobs (single-GPU queue), media | `microdrama/backend/` |
| **Frontend** | React + Vite "Director's Console" SPA | `frontend/` |

The ComfyUI workflow wrappers talk to ComfyUI over HTTP, so they run in this
project's own env — independent of ComfyUI's `comfy` conda env and of Wan2GP.

## The Phase A functions (usable on their own)

```python
from microdrama.comfy import generate_image, edit_image, generate_microdrama

# text -> image (Z-Image Turbo)  -> outputs/images/
img = generate_image("a rain-soaked neon alley at night, cinematic")[0]

# edit / composite 1..N reference images (Flux-2 Klein) -> outputs/edits/
edit = edit_image([img, "character.png"], "place the detective under the neon sign")[0]

# full micro-drama with timeline + audio (LTX Director) -> outputs/videos/
generate_microdrama(
    global_prompt="film-noir detective story, cinematic",
    segments=[
        {"type": "text",  "prompt": "a detective sits at his desk, rain outside", "length_frames": 25},
        {"type": "image", "prompt": "he stands and walks to the window",
         "length_frames": 24, "image_path": img, "guide_strength": 1.0},
    ],
    audio=[{"audio_path": "line.wav", "start": 0, "length": 49}],  # optional
)
```

## Prerequisites

- **ComfyUI** at `http://localhost:8188` with the LTX-2.3, Z-Image, and Flux-2
  Klein models installed (this repo's workflows reference them). Launched via
  `ComfyUI/start.bat` (conda env `comfy`).
- **gpt-5-mini** on an OpenAI-compatible server at `http://localhost:3000/v1`.
- A dedicated conda env **`microdrama`** (Python 3.11) for this project.
- Hardware here is an 8GB RTX 4070 Laptop, so heavy GPU steps are **serialized**
  (the job queue runs one at a time and frees ComfyUI's models before TTS/LTX).

## Setup

```bash
conda create -n microdrama python=3.11 -y
conda activate microdrama
pip install -r requirements.txt          # backend + ComfyUI wrappers
# Voice (ported OmniVoice). Install matching CUDA torch first:
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu130
pip install -r requirements-tts.txt      # transformers pinned to 4.54.0
# OmniVoice weights download automatically on first synth, or:
python -c "from microdrama.tts import tts; tts.download_weights()"

cd frontend && npm install && cd ..
```

## Generate the preset library

```bash
python scripts/generate_presets.py            # text library (LLM only)
python scripts/generate_presets.py --all       # + render portraits & voice clips (GPU)
```

## Characters & scene scripts

- **Casting** (button in the Studio): create a character with a name, description,
  look prompt and voice tags (or hit **🎲 Random** to have the director invent
  one), then **generate** a portrait (Z-Image) and a **voice sample** (OmniVoice)
  — each independently **rerollable**, or **⤒ upload** your own portrait / voice
  clip. An uploaded voice clip becomes the character's sample **and** a clone
  reference: scenes that character is in are voiced by cloning that clip (first
  use downloads Whisper-medium for reference transcription). Characters persist
  in the `characters` preset library.
- **Uploads everywhere**: scene cards have **⤒ upload guide image** (sets the shot's
  still), and characters have upload buttons for portrait and voice.
- **Character-consistent scenes**: attach characters to a shot (chips on the scene
  card). When that shot's guide still is generated, the characters' portraits are
  used as **multi-reference inputs** (Flux) so they look consistent across scenes.
- **Scene script** (per shot): supply a *concept* and *dialogue*, and the director
  generates the rich, plain-text **video prompt grounded in the shot's guide image**
  (sent to the LLM as a vision input; falls back to text-only if the endpoint has no
  vision). The result appears in a **copy box** and is used as the shot's LTX prompt.

## Run

One click — starts ComfyUI (if down), the backend, and the frontend:

```bat
start.bat            ::  Windows (double-click, or run in cmd)
```
```bash
bash start.sh        #   WSL / git-bash / Linux / macOS
```
Then open **http://localhost:5173** (API at http://localhost:8000/docs).

- `start.bat` activates the `microdrama` conda env and runs `scripts/start_all.py`,
  opening ComfyUI + backend + frontend each in its own console.
- `start.sh` auto-starts ComfyUI on git-bash, then runs backend + frontend in the
  background (logs in `./logs`; stop with `kill $(cat logs/*.pid)`).
- Override paths via env vars: `MICRODRAMA_PY`, `COMFY_ROOT`, `COMFY_URL`, `LLM_BASE_URL`.

Manual alternative:
```bash
python -m uvicorn microdrama.backend.app:app --port 8000
cd frontend && npm run dev
```

## Validate Phase A

```bash
python scripts/smoke_test.py            # t2i + edit
python scripts/smoke_test.py all        # + multi-ref edit + a short LTX render
```
Outputs land in `outputs/{images,edits,videos}`.

## Third-party code and models

The TTS worker expects a port of the OmniVoice pipeline at `microdrama/tts/_vendor/`
(OmniVoice by Xiaomi, Qwen3 modeling by the Qwen team / Hugging Face, Higgs audio
tokenizer by Boson AI, plus helpers from [Wan2GP](https://github.com/deepbeepmeep/Wan2GP)).
That code is not included in this repository; copy `omnivoice/` and `shared/` from a
local Wan2GP checkout into `microdrama/tts/_vendor/` and follow their licenses.
Model weights, generated media and outputs are also not tracked.
