"""Minimal, robust ComfyUI API client.

Talks to ComfyUI purely over HTTP/WebSocket, so it runs in this project's own
env (no dependency on ComfyUI's `comfy` conda env). Covers everything the
workflow wrappers need: queue a prompt, wait for it (WS progress + polling
fallback), download outputs, upload inputs, and free GPU/RAM between heavy jobs.
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable

import requests

from .. import config

ProgressCb = Callable[[dict], None]

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_JPEG_SIG = b"\xff\xd8\xff"


def _extract_preview_image(frame: bytes) -> bytes | None:
    """ComfyUI prepends a variable-length binary header (event type, and in
    newer versions JSON metadata) before the preview image. Locate the real
    PNG/JPEG signature and return from there, so we don't depend on header size."""
    i = frame.find(_PNG_SIG)
    if i != -1:
        return frame[i:]
    j = frame.find(_JPEG_SIG)
    if j != -1:
        return frame[j:]
    return None


class ComfyError(RuntimeError):
    """Raised when ComfyUI rejects a prompt or a node errors during execution."""


class ComfyClient:
    # Output keys in /history that point at saved files.
    _FILE_KEYS = ("images", "gifs", "video", "videos", "audio")

    def __init__(self, base_url: str | None = None, client_id: str | None = None,
                 timeout: float = 30.0):
        self.base_url = (base_url or config.COMFY_URL).rstrip("/")
        self.client_id = client_id or uuid.uuid4().hex
        self.timeout = timeout
        self._ws_url = self.base_url.replace("http", "ws", 1) + "/ws"

    # --- low-level helpers ------------------------------------------------
    def _get(self, path: str, **kw) -> requests.Response:
        r = requests.get(self.base_url + path, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r

    def _post(self, path: str, **kw) -> requests.Response:
        r = requests.post(self.base_url + path, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r

    def is_up(self) -> bool:
        try:
            self._get("/system_stats")
            return True
        except Exception:
            return False

    # --- queue / execute --------------------------------------------------
    def submit(self, workflow: dict) -> str:
        """Queue an API-format workflow graph. Returns the prompt_id."""
        payload = {"prompt": workflow, "client_id": self.client_id}
        r = requests.post(self.base_url + "/prompt", json=payload, timeout=self.timeout)
        if r.status_code != 200:
            # ComfyUI returns rich validation errors as JSON.
            try:
                err = r.json()
            except Exception:
                err = {"error": r.text}
            raise ComfyError(f"Prompt rejected: {json.dumps(err, indent=2)[:2000]}")
        return r.json()["prompt_id"]

    def wait(self, prompt_id: str, on_progress: ProgressCb | None = None,
             timeout: float = 3600.0,
             on_preview: Callable[[bytes], None] | None = None) -> dict:
        """Block until the prompt finishes; return its /history entry.

        Uses the WebSocket for liveness/progress when possible, and always
        confirms completion via /history (the source of truth for outputs).
        ``on_preview`` receives each live sampling preview frame (image bytes).
        """
        deadline = time.time() + timeout
        try:
            self._wait_ws(prompt_id, on_progress, deadline, on_preview)
        except Exception:
            # WS unavailable or dropped: fall back to pure polling.
            self._wait_poll(prompt_id, deadline)
        entry = self.history(prompt_id)
        if not entry:
            # WS said done but history empty -> poll a little longer.
            self._wait_poll(prompt_id, deadline)
            entry = self.history(prompt_id)
        self._raise_for_status(prompt_id, entry)
        return entry

    def _wait_ws(self, prompt_id: str, on_progress: ProgressCb | None, deadline: float,
                 on_preview: Callable[[bytes], None] | None = None) -> None:
        from websocket import create_connection  # websocket-client

        ws = create_connection(f"{self._ws_url}?clientId={self.client_id}", timeout=60)
        try:
            while True:
                if time.time() > deadline:
                    raise TimeoutError(f"Timed out waiting for prompt {prompt_id}")
                ws.settimeout(max(1.0, deadline - time.time()))
                msg = ws.recv()
                if isinstance(msg, bytes):  # binary sampling-preview frame
                    if on_preview:
                        img = _extract_preview_image(msg)
                        if img:
                            try:
                                on_preview(img)
                            except Exception:
                                pass
                    continue
                data = json.loads(msg)
                mtype, payload = data.get("type"), data.get("data", {})
                pid = payload.get("prompt_id")
                if mtype in ("progress", "executing", "execution_cached", "status") and on_progress:
                    on_progress(data)
                if mtype == "executing" and payload.get("node") is None and pid == prompt_id:
                    return  # this prompt finished
                if mtype == "execution_error" and pid == prompt_id:
                    raise ComfyError(f"Execution error: {json.dumps(payload)[:2000]}")
                if mtype == "execution_success" and pid == prompt_id:
                    return
        finally:
            try:
                ws.close()
            except Exception:
                pass

    def _wait_poll(self, prompt_id: str, deadline: float, interval: float = 2.0) -> None:
        while time.time() < deadline:
            if self.history(prompt_id):
                return
            time.sleep(interval)
        raise TimeoutError(f"Timed out waiting for prompt {prompt_id}")

    def history(self, prompt_id: str) -> dict:
        data = self._get(f"/history/{prompt_id}").json()
        return data.get(prompt_id, {})

    @staticmethod
    def _raise_for_status(prompt_id: str, entry: dict) -> None:
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            msgs = status.get("messages", [])
            raise ComfyError(f"Prompt {prompt_id} failed: {json.dumps(msgs)[:2000]}")

    # --- outputs ----------------------------------------------------------
    def iter_output_files(self, entry: dict) -> Iterable[dict]:
        """Yield {filename, subfolder, type} dicts from a /history entry."""
        for node_out in entry.get("outputs", {}).values():
            for key in self._FILE_KEYS:
                for item in node_out.get(key, []) or []:
                    if isinstance(item, dict) and item.get("filename"):
                        yield item

    def view(self, filename: str, subfolder: str = "", type_: str = "output") -> bytes:
        params = {"filename": filename, "subfolder": subfolder, "type": type_}
        return self._get("/view", params=params).content

    def download_outputs(self, prompt_id: str, out_dir: Path | str,
                         prefix: str = "") -> list[Path]:
        """Download every output file of a finished prompt into out_dir."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        entry = self.history(prompt_id)
        saved: list[Path] = []
        for item in self.iter_output_files(entry):
            data = self.view(item["filename"], item.get("subfolder", ""),
                             item.get("type", "output"))
            dest = out_dir / f"{prefix}{item['filename']}"
            dest.write_bytes(data)
            saved.append(dest)
        return saved

    # --- inputs -----------------------------------------------------------
    def upload(self, path: Path | str, subfolder: str = "", type_: str = "input",
               overwrite: bool = True) -> str:
        """Upload a file to ComfyUI's input area; return the stored filename.

        Tries the HTTP endpoint first, then falls back to copying straight into
        ComfyUI's input dir (valid because we run on the same machine).
        """
        path = Path(path)
        try:
            with open(path, "rb") as fh:
                files = {"image": (path.name, fh)}
                data = {"type": type_, "subfolder": subfolder,
                        "overwrite": str(overwrite).lower()}
                r = self._post("/upload/image", files=files, data=data)
            info = r.json()
            name = info.get("name", path.name)
            sub = info.get("subfolder", "")
            return f"{sub}/{name}" if sub else name
        except Exception:
            dest_dir = config.COMFY_INPUT_DIR / subfolder
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest_dir / path.name)
            return f"{subfolder}/{path.name}" if subfolder else path.name

    # --- memory management ------------------------------------------------
    def free(self, unload_models: bool = True, free_memory: bool = True) -> None:
        """Ask ComfyUI to unload models / free VRAM+RAM (used between heavy jobs)."""
        try:
            self._post("/free", json={"unload_models": unload_models,
                                      "free_memory": free_memory})
        except Exception:
            pass  # best-effort

    def interrupt(self) -> None:
        try:
            self._post("/interrupt")
        except Exception:
            pass


def load_workflow(name: str) -> dict:
    """Load an API-format workflow template from workflows/ by file name."""
    with open(config.WORKFLOWS_DIR / name, "r", encoding="utf-8") as fh:
        return json.load(fh)
