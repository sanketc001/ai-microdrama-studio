"""gpt-5-mini "director" client (OpenAI-compatible endpoint at :3000/v1).

Writes the branching narrative and compiles it into render parameters. All
methods return parsed Python dicts following the contracts in ``prompts.py``.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from .. import config
from . import prompts


_SCRIPT_FALLBACK_SYSTEM = (
    "You are a cinematographer. Write a single, vivid, plain-English shot "
    "description that follows the user's specification exactly. Output ONLY prose "
    "— no JSON, no markdown, no headings, no bullet points."
)


def _prose(text: str) -> str:
    """Scene scripts must be plain prose; if the model returns JSON, flatten its
    string values (in order) into paragraphs."""
    t = (text or "").strip()
    if t[:1] in ("{", "["):
        try:
            data = json.loads(t)

            def walk(v):
                if isinstance(v, str):
                    return [v]
                if isinstance(v, list):
                    return [x for item in v for x in walk(item)]
                if isinstance(v, dict):
                    return [x for item in v.values() for x in walk(item)]
                return []

            parts = [p.strip() for p in walk(data) if isinstance(p, str) and p.strip()]
            if parts:
                t = "\n\n".join(parts)
        except Exception:
            pass
    t = re.sub(r"\*\*(.*?)\*\*", r"\1", t)       # strip bold markers
    t = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", t)   # strip markdown headings
    return t.strip()


def _image_data_url(path, max_dim: int = 512, quality: int = 72) -> str:
    """Downscale + JPEG-compress an image to a small data URL. The local proxy
    rejects large request bodies (~100KB), so vision needs a compact payload."""
    import io as _io
    from PIL import Image
    img = Image.open(path).convert("RGB")
    img.thumbnail((max_dim, max_dim))
    buf = _io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _parse_json(text: str) -> dict:
    """Best-effort extraction of a JSON object from a model response."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model response: {text[:300]!r}")
    return json.loads(text[start:end + 1])


class DirectorLLM:
    def __init__(self, base_url: str | None = None, model: str | None = None,
                 api_key: str | None = None):
        from openai import OpenAI
        self.model = model or config.LLM_MODEL
        self.client = OpenAI(base_url=base_url or config.LLM_BASE_URL,
                             api_key=api_key or config.LLM_API_KEY)

    # --- core --------------------------------------------------------------
    def complete_json(self, system: str, user: str, *, temperature: float = 0.8,
                      max_tokens: int = 2000) -> dict:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            resp = self.client.chat.completions.create(
                response_format={"type": "json_object"}, **kwargs)
        except Exception:
            # Some local servers reject response_format — retry without it.
            resp = self.client.chat.completions.create(**kwargs)
        return _parse_json(resp.choices[0].message.content)

    def complete_text(self, system: str, user: str, *, temperature: float = 0.8,
                      max_tokens: int = 600) -> str:
        resp = self.client.chat.completions.create(
            model=self.model, temperature=temperature, max_tokens=max_tokens,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
        return (resp.choices[0].message.content or "").strip()

    # --- narrative ---------------------------------------------------------
    @staticmethod
    def _preset_context(characters: list[dict] | None, scenes: list[dict] | None) -> str:
        parts = []
        if characters:
            parts.append("Available characters:\n" + "\n".join(
                f"- {c.get('name')}: {c.get('description','')}" for c in characters))
        if scenes:
            parts.append("Available scenes/sets:\n" + "\n".join(
                f"- {s.get('name')}: {s.get('description','')}" for s in scenes))
        return "\n\n".join(parts)

    def propose_story(self, premise: str, *, characters: list[dict] | None = None,
                      scenes: list[dict] | None = None) -> dict:
        ctx = self._preset_context(characters, scenes)
        user = (f"Premise: {premise}\n\n{ctx}\n\n" if ctx else f"Premise: {premise}\n\n") + \
            "Propose a short micro-drama and ways the viewer can steer it."
        return self.complete_json(prompts.DIRECTOR_PERSONA + "\n\n" + prompts.STORY_CONTRACT, user)

    def expand_choice(self, story_state: dict, user_input: str) -> dict:
        user = (
            "Current story so far (JSON):\n" + json.dumps(story_state, ensure_ascii=False) +
            f"\n\nThe viewer steers the story with: {user_input}\n\n"
            "Continue the story accordingly and offer new choices."
        )
        return self.complete_json(prompts.DIRECTOR_PERSONA + "\n\n" + prompts.STORY_CONTRACT, user)

    def compile_timeline(self, story_state: dict) -> dict:
        user = ("Story (JSON):\n" + json.dumps(story_state, ensure_ascii=False) +
                "\n\nCompile this into a renderable timeline.")
        return self.complete_json(prompts.DIRECTOR_PERSONA + "\n\n" + prompts.TIMELINE_CONTRACT,
                                  user, temperature=0.6)

    def random_character(self, hint: str = "") -> dict:
        """Invent one original character (name, description, look prompt, voice
        tags, sample line) for the casting form."""
        user = (
            "Invent ONE original, vivid, castable character for a micro-drama. "
            'Return JSON {"name":str,"description":str,"look_prompt":str,"voice":str,"sample_text":str}. '
            '"look_prompt" is a detailed portrait text-to-image prompt. "sample_text" is one short '
            "line (<= 12 words) the character might say. " + prompts.VOICE_TAGS
        )
        if hint.strip():
            user += f"\nLean into this idea: {hint.strip()}"
        data = self.complete_json(prompts.DIRECTOR_PERSONA, user, temperature=1.0)
        return {k: (data.get(k) or "") for k in
                ("name", "description", "look_prompt", "voice", "sample_text")}

    def scene_script(self, image_path: str | Path | None, concept: str = "",
                     dialogue: str = "", *, temperature: float = 0.85,
                     max_tokens: int = 1000) -> str:
        """Generate the rich plain-text LTX video prompt for a shot, grounded in
        its guide image (multimodal). Falls back to text-only if the endpoint
        does not accept image input."""
        tmpl = (prompts.SCENE_SCRIPT_PROMPT
                .replace("{concept}", concept.strip() or "(director's choice — invent a fitting motion)")
                .replace("{dialogue}", dialogue.strip() or "(no spoken dialogue — soundscape only)"))
        if image_path and Path(image_path).exists():
            try:
                content = [
                    {"type": "text", "text": tmpl},
                    {"type": "image_url", "image_url": {"url": _image_data_url(image_path)}},
                ]
                resp = self.client.chat.completions.create(
                    model=self.model, temperature=temperature, max_tokens=max_tokens,
                    messages=[{"role": "user", "content": content}])
                text = (resp.choices[0].message.content or "").strip()
                if text:
                    return _prose(text)
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "scene_script vision call failed, using text fallback: %s", exc)
        return _prose(self.complete_text(
            _SCRIPT_FALLBACK_SYSTEM,
            tmpl + "\n\n(No image is attached; infer a plausible opening frame from the idea.)",
            temperature=temperature, max_tokens=max_tokens))
