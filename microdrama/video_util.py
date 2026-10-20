"""Small video helpers (PyAV). Used to chain shots by seeding the next one with
the last frame of a rendered clip."""
from __future__ import annotations

from pathlib import Path


def extract_last_frame(video_path: str | Path, out_path: str | Path) -> Path:
    """Decode ``video_path`` and save its final frame as an image at out_path."""
    import av

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    last = None
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        for frame in container.decode(stream):
            last = frame
    if last is None:
        raise RuntimeError(f"no video frames in {video_path}")
    last.to_image().save(out_path)
    return out_path
