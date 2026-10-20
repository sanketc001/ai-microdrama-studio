"""Text-to-image via the Z-Image Turbo workflow (T2I-ZImageTurbo.json).

Used to generate character/scene reference images from a prompt.
"""
from __future__ import annotations

import copy
from pathlib import Path

from .. import config
from .client import ComfyClient, ProgressCb, load_workflow
from ._common import rand_seed, run_workflow

_TEMPLATE = "t2i_zimage.json"


def generate_image(
    prompt: str,
    *,
    negative: str = config.DEFAULT_IMAGE_NEGATIVE,
    width: int = 960,
    height: int = 544,
    seed: int | None = None,
    steps: int = 9,
    cfg: float = 1.0,
    sampler: str = "res_multistep",
    scheduler: str = "simple",
    denoise: float = 1.0,
    batch_size: int = 1,
    filename_prefix: str = "microdrama/img",
    out_dir: Path | str = config.IMAGES_DIR,
    models: dict | None = None,
    client: ComfyClient | None = None,
    on_progress: ProgressCb | None = None,
    timeout: float = 600.0,
) -> list[Path]:
    """Generate image(s) from ``prompt``. Returns paths to the saved files."""
    g = copy.deepcopy(load_workflow(_TEMPLATE))
    seed = rand_seed() if seed is None else seed
    m = {**config.ZIMAGE_MODELS, **(models or {})}

    g["6"]["inputs"]["text"] = prompt
    g["7"]["inputs"]["text"] = negative
    g["3"]["inputs"].update(
        seed=seed, steps=steps, cfg=cfg,
        sampler_name=sampler, scheduler=scheduler, denoise=denoise,
    )
    g["13"]["inputs"].update(width=width, height=height, batch_size=batch_size)
    g["9"]["inputs"]["filename_prefix"] = filename_prefix
    g["16"]["inputs"]["unet_name"] = m["unet"]
    g["17"]["inputs"]["vae_name"] = m["vae"]
    g["18"]["inputs"]["clip_name"] = m["clip"]

    return run_workflow(g, out_dir, prefix="", client=client,
                        on_progress=on_progress, timeout=timeout)
