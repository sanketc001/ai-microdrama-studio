"""Image editing / compositing via Flux-2 Klein (single- and multi-reference).

Generalizes the single- and multi-image Flux2 Klein edit workflows: every input
image is VAE-encoded and stacked as a ReferenceLatent onto both the positive
(edit prompt) and negative conditioning. With one image it behaves like the
single-reference edit; with several it composites them — e.g. place a specific
character into a scene, change an appearance, or combine multiple characters.
"""
from __future__ import annotations

from pathlib import Path

from .. import config
from .client import ComfyClient, ProgressCb
from ._common import rand_seed, run_workflow


def edit_image(
    images: str | Path | list[str | Path],
    prompt: str,
    *,
    negative: str = "",
    steps: int = 20,
    cfg: float = 5.0,
    seed: int | None = None,
    megapixels: float = 1.0,
    sampler: str = "euler",
    filename_prefix: str = "microdrama/edit",
    out_dir: Path | str = config.EDITS_DIR,
    models: dict | None = None,
    client: ComfyClient | None = None,
    on_progress: ProgressCb | None = None,
    timeout: float = 900.0,
) -> list[Path]:
    """Edit/composite one or more reference ``images`` guided by ``prompt``.

    The first image is the primary one (defines output dimensions).
    """
    if isinstance(images, (str, Path)):
        images = [images]
    if not images:
        raise ValueError("edit_image requires at least one reference image")

    client = client or ComfyClient()
    seed = rand_seed() if seed is None else seed
    m = {**config.FLUX_MODELS, **(models or {})}

    # Upload every reference image into ComfyUI's input area.
    names = [client.upload(p) for p in images]

    g: dict = {
        "unet": {"class_type": "UNETLoader",
                 "inputs": {"unet_name": m["unet"], "weight_dtype": "default"}},
        "clip": {"class_type": "CLIPLoader",
                 "inputs": {"clip_name": m["clip"], "type": "flux2", "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": m["vae"]}},
        "pos_text": {"class_type": "CLIPTextEncode",
                     "inputs": {"text": prompt, "clip": ["clip", 0]}},
        "neg_text": {"class_type": "CLIPTextEncode",
                     "inputs": {"text": negative, "clip": ["clip", 0]}},
        "sampler_sel": {"class_type": "KSamplerSelect",
                        "inputs": {"sampler_name": sampler}},
        "noise": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
    }

    # Per-image: load -> scale to target pixels -> VAE encode.
    encs: list[str] = []
    for i, name in enumerate(names):
        load, scale, enc = f"load_{i}", f"scale_{i}", f"enc_{i}"
        g[load] = {"class_type": "LoadImage", "inputs": {"image": name}}
        g[scale] = {"class_type": "ImageScaleToTotalPixels",
                    "inputs": {"upscale_method": "lanczos", "megapixels": megapixels,
                               "resolution_steps": 1, "image": [load, 0]}}
        g[enc] = {"class_type": "VAEEncode",
                  "inputs": {"pixels": [scale, 0], "vae": ["vae", 0]}}
        encs.append(enc)

    primary_scale = "scale_0"
    g["size"] = {"class_type": "GetImageSize", "inputs": {"image": [primary_scale, 0]}}
    g["latent_img"] = {"class_type": "EmptyFlux2LatentImage",
                       "inputs": {"width": ["size", 0], "height": ["size", 1], "batch_size": 1}}
    g["sched"] = {"class_type": "Flux2Scheduler",
                  "inputs": {"steps": steps, "width": ["size", 0], "height": ["size", 1]}}

    # Stack reference latents onto positive and negative conditioning.
    def _stack(start_node: str, tag: str):
        cond = [start_node, 0]
        for i, enc in enumerate(encs):
            rid = f"{tag}_ref_{i}"
            g[rid] = {"class_type": "ReferenceLatent",
                      "inputs": {"conditioning": cond, "latent": [enc, 0]}}
            cond = [rid, 0]
        return cond

    positive = _stack("pos_text", "pos")
    negative_c = _stack("neg_text", "neg")

    g["guider"] = {"class_type": "CFGGuider",
                   "inputs": {"cfg": cfg, "model": ["unet", 0],
                              "positive": positive, "negative": negative_c}}
    g["sample"] = {"class_type": "SamplerCustomAdvanced",
                   "inputs": {"noise": ["noise", 0], "guider": ["guider", 0],
                              "sampler": ["sampler_sel", 0], "sigmas": ["sched", 0],
                              "latent_image": ["latent_img", 0]}}
    g["decode"] = {"class_type": "VAEDecode",
                   "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]}}
    g["save"] = {"class_type": "SaveImage",
                 "inputs": {"filename_prefix": filename_prefix, "images": ["decode", 0]}}

    return run_workflow(g, out_dir, client=client, on_progress=on_progress, timeout=timeout)
