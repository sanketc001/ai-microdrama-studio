"""One-command launcher for the AI Microdrama Studio (Windows).

- Starts ComfyUI via its own start.bat if :8188 is down, and waits for it.
- Launches the FastAPI backend (uvicorn :8000) and the Vite frontend (:5173),
  each in its own console window.
- Warns if the gpt-5-mini director endpoint (:3000) is unreachable.

    python scripts/start_all.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from microdrama import config

FRONTEND_DIR = config.PROJECT_ROOT / "frontend"


def _up(url: str, timeout: float = 3.0) -> bool:
    try:
        requests.get(url, timeout=timeout)
        return True
    except Exception:
        return False


def _new_console(title: str, command: str, cwd: Path) -> None:
    # `start` opens a separate, persistent console window on Windows.
    subprocess.Popen(f'start "{title}" cmd /k {command}', cwd=str(cwd), shell=True)


def ensure_comfyui() -> bool:
    if _up(config.COMFY_URL + "/system_stats"):
        print(f"[ok] ComfyUI already running at {config.COMFY_URL}")
        return True
    if not config.COMFY_START_BAT.exists():
        print(f"[!] ComfyUI not running and start.bat not found at {config.COMFY_START_BAT}")
        return False
    print(f"[..] Launching ComfyUI via {config.COMFY_START_BAT}")
    _new_console("ComfyUI", str(config.COMFY_START_BAT), config.COMFY_ROOT)
    for i in range(90):  # up to ~3 minutes
        time.sleep(2)
        if _up(config.COMFY_URL + "/system_stats"):
            print(f"[ok] ComfyUI is up after ~{i * 2}s")
            return True
        if i % 5 == 0:
            print(f"     waiting for ComfyUI… ({i * 2}s)")
    print("[!] ComfyUI did not come up in time — check its window.")
    return False


def main():
    print("=== AI Microdrama Studio — launcher ===")
    ensure_comfyui()

    if _up(config.LLM_BASE_URL.replace("/v1", "") + "/", timeout=2):
        print(f"[ok] Director LLM reachable near {config.LLM_BASE_URL}")
    else:
        print(f"[!] Director LLM ({config.LLM_BASE_URL}) unreachable — start your gpt-5-mini server.")

    print("[..] Starting backend (uvicorn :8000)")
    _new_console("Microdrama API",
                 f'"{sys.executable}" -m uvicorn microdrama.backend.app:app --port 8000',
                 config.PROJECT_ROOT)

    print("[..] Starting frontend (vite :5173)")
    _new_console("Microdrama UI", "npm run dev", FRONTEND_DIR)

    print("\nOpen the studio at  http://localhost:5173")
    print("API docs at         http://localhost:8000/docs")


if __name__ == "__main__":
    main()
