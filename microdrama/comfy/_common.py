"""Shared helpers for the ComfyUI workflow wrappers."""
from __future__ import annotations

import random
from pathlib import Path
from typing import Callable

from .client import ComfyClient, ProgressCb

MAX_SEED = 2**63 - 1


def rand_seed() -> int:
    return random.randint(0, MAX_SEED)


def run_workflow(graph: dict, out_dir: Path | str, *, prefix: str = "",
                 client: ComfyClient | None = None,
                 on_progress: ProgressCb | None = None,
                 on_preview: Callable[[bytes], None] | None = None,
                 timeout: float = 3600.0) -> list[Path]:
    """Submit a graph, wait for completion, download outputs to out_dir."""
    client = client or ComfyClient()
    prompt_id = client.submit(graph)
    client.wait(prompt_id, on_progress=on_progress, timeout=timeout, on_preview=on_preview)
    return client.download_outputs(prompt_id, out_dir, prefix=prefix)
