"""Phase A smoke test — exercises the workflow wrappers against live ComfyUI.

Usage (from project root, in the `microdrama` conda env):
    python scripts/smoke_test.py            # t2i + edit (fast)
    python scripts/smoke_test.py all        # + multi-ref edit + LTX render
    python scripts/smoke_test.py t2i edit multi ltx   # pick stages

Each stage prints the files it saved so you can confirm they land in outputs/.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from microdrama import config
from microdrama.comfy import ComfyClient, generate_image, edit_image, generate_microdrama


def _progress(label: str):
    last = {"v": -1}

    def cb(msg: dict):
        t = msg.get("type")
        d = msg.get("data", {})
        if t == "progress":
            v, m = d.get("value", 0), d.get("max", 1)
            pct = int(100 * v / max(1, m))
            if pct != last["v"]:
                last["v"] = pct
                print(f"\r  [{label}] {pct:3d}%  (step {v}/{m})", end="", flush=True)
        elif t == "executing" and d.get("node"):
            print(f"\r  [{label}] running node {d['node']}            ", end="", flush=True)
    return cb


def stage_t2i(client) -> Path:
    print("\n== T2I (Z-Image Turbo) ==")
    t = time.time()
    out = generate_image(
        "a cozy dimly lit detective office at night, rain on the window, "
        "cinematic, moody lighting, film still",
        width=768, height=448, steps=8, client=client, on_progress=_progress("t2i"),
    )
    print(f"\n  saved: {[str(p) for p in out]}  ({time.time()-t:.0f}s)")
    return out[0]


def stage_edit(client, src: Path) -> Path:
    print("\n== Edit (Flux2 Klein, single reference) ==")
    t = time.time()
    out = edit_image(src, "make it daytime, warm sunlight through the window",
                     steps=12, client=client, on_progress=_progress("edit"))
    print(f"\n  saved: {[str(p) for p in out]}  ({time.time()-t:.0f}s)")
    return out[0]


def stage_multi(client, scene: Path) -> Path:
    print("\n== Multi-reference edit (compose two images) ==")
    char = generate_image(
        "full-body portrait of a weary detective in a trench coat, neutral background",
        width=448, height=768, steps=8, client=client, on_progress=_progress("char"),
    )[0]
    print()
    t = time.time()
    out = edit_image([scene, char], "place the detective standing in the office",
                     steps=12, client=client, on_progress=_progress("multi"))
    print(f"\n  saved: {[str(p) for p in out]}  ({time.time()-t:.0f}s)")
    return out[0]


def stage_ltx(client, scene: Path):
    print("\n== LTX micro-drama (short render — this can take minutes) ==")
    client.free()  # clear image models before the big LTX model loads
    t = time.time()
    out = generate_microdrama(
        global_prompt="a film-noir detective story, cinematic, moody lighting",
        segments=[
            {"type": "text", "prompt": "a detective sits at his desk, rain outside",
             "length_frames": 25},
            {"type": "image", "prompt": "the detective stands and walks to the window",
             "length_frames": 24, "image_path": str(scene), "guide_strength": 1.0},
        ],
        frame_rate=24, base_steps=8, refine_steps=4,
        client=client, on_progress=_progress("ltx"), timeout=2400,
    )
    print(f"\n  saved: {[str(p) for p in out]}  ({time.time()-t:.0f}s)")


def main():
    stages = sys.argv[1:] or ["t2i", "edit"]
    if "all" in stages:
        stages = ["t2i", "edit", "multi", "ltx"]
    config.ensure_dirs()
    client = ComfyClient()
    if not client.is_up():
        print(f"ComfyUI not reachable at {client.base_url} — start it first.")
        sys.exit(1)
    print(f"ComfyUI is up at {client.base_url}. Stages: {stages}")

    scene = None
    if "t2i" in stages:
        scene = stage_t2i(client)
    if "edit" in stages:
        scene = stage_edit(client, scene or _need_scene())
    if "multi" in stages:
        stage_multi(client, scene or _need_scene())
    if "ltx" in stages:
        stage_ltx(client, scene or _need_scene())
    print("\nDone.")


def _need_scene() -> Path:
    existing = sorted(config.IMAGES_DIR.glob("*.png"))
    if existing:
        print(f"  (reusing existing scene image {existing[-1].name})")
        return existing[-1]
    raise SystemExit("This stage needs a scene image — include 't2i' in the stages.")


if __name__ == "__main__":
    main()
