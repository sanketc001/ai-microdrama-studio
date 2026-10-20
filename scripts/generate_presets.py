"""Generate the starter preset library with gpt-5-mini.

Text library (characters, scenes, voices, dialogues, storylines) is authored by
the LLM and needs no GPU. Asset rendering (character portraits, scene stills,
voice samples) is GPU-bound and opt-in.

    python scripts/generate_presets.py                 # text library only
    python scripts/generate_presets.py --images        # + render portraits/scene stills
    python scripts/generate_presets.py --voices        # + render sample voice clips
    python scripts/generate_presets.py --all
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from microdrama import config
from microdrama.director import DirectorLLM
from microdrama.director.prompts import DIRECTOR_PERSONA
from microdrama.presets import store

_CONTRACTS = {
    "characters": """Invent {n} distinct, vivid characters for a micro-drama studio.
Return JSON {"items":[{"name":str,"description":str,"look_prompt":str,"voice":str}]}.
"look_prompt" is a detailed text-to-image prompt for a portrait. "voice" is
OmniVoice voice-design tags (e.g. "male, middle-aged, gravelly, slight accent").""",
    "scenes": """Invent {n} distinct cinematic scenes/sets for micro-dramas.
Return JSON {"items":[{"name":str,"description":str,"setting_prompt":str,"mood":str}]}.
"setting_prompt" is a detailed text-to-image prompt for an establishing still.""",
    "voices": """Invent {n} reusable voice styles for OmniVoice TTS.
Return JSON {"items":[{"name":str,"tags":str,"sample_text":str}]}.
"tags" are comma-separated OmniVoice voice-design tags; "sample_text" is a short
line (may include tags like [laughter]) demonstrating the voice.""",
    "dialogues": """Write {n} short, reusable dialogue snippets a viewer might pick.
Return JSON {"items":[{"name":str,"speaker":str,"text":str,"voice":str}]}.""",
    "storylines": """Invent {n} micro-drama storylines viewers can start from.
Return JSON {"items":[{"title":str,"logline":str,"premise":str,
"beats":[{"summary":str,"scene":str}],"suggested_characters":[str],"suggested_scenes":[str]}]}.""",
}
_COUNTS = {"characters": 6, "scenes": 6, "voices": 6, "dialogues": 8, "storylines": 5}


def generate_text_library(d: DirectorLLM) -> dict[str, list[dict]]:
    library: dict[str, list[dict]] = {}
    for kind, contract in _CONTRACTS.items():
        n = _COUNTS[kind]
        print(f"  generating {n} {kind} ...")
        data = d.complete_json(DIRECTOR_PERSONA, contract.replace("{n}", str(n)) +
                               '\nReturn ONLY the JSON object.', max_tokens=3000)
        items = data.get("items", data if isinstance(data, list) else [])
        for it in items:
            it["id"] = uuid.uuid4().hex[:12]
            it["custom"] = False
        library[kind] = items
        print(f"    -> {len(items)} {kind}")
    return library


def render_images(client=None):
    from microdrama.comfy import generate_image
    for kind, key in (("characters", "look_prompt"), ("scenes", "setting_prompt")):
        items = store.load(kind)
        for it in items:
            if it.get("image") or not it.get(key):
                continue
            print(f"  rendering {kind} image: {it.get('name')}")
            out = generate_image(it[key], width=768, height=768 if kind == "characters" else 448,
                                 filename_prefix=f"presets/{kind}", client=client)
            it["image"] = str(out[0]) if out else None
        store.save(kind, items)


def render_voices():
    from microdrama.tts.tts import synthesize
    voices = store.load("voices")
    lines = [{"text": v.get("sample_text") or "Hello, this is a sample of my voice.",
              "alt_prompt": v.get("tags", ""), "audio_prompt_type": "",
              "out_path": str(config.AUDIO_DIR / f"voice_{v['id']}.wav")}
             for v in voices if not v.get("sample")]
    if not lines:
        return
    synthesize(lines)
    for v, line in zip([v for v in voices if not v.get("sample")], lines):
        v["sample"] = line["out_path"]
    store.save("voices", voices)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", action="store_true")
    ap.add_argument("--voices", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true", help="regenerate text even if files exist")
    args = ap.parse_args()
    config.ensure_dirs()

    if args.force or not (config.PRESETS_DIR / "characters.json").exists():
        print("Generating text preset library with gpt-5-mini ...")
        library = generate_text_library(DirectorLLM())
        store.seed_if_empty(library) if not args.force else [store.save(k, v) for k, v in library.items()]
        print("Saved presets to", config.PRESETS_DIR)
    else:
        print("Text presets already exist (use --force to regenerate).")

    if args.images or args.all:
        print("Rendering preset images ...")
        render_images()
    if args.voices or args.all:
        print("Rendering preset voice samples ...")
        render_voices()
    print("Done.")


if __name__ == "__main__":
    main()
