"""ComfyUI HTTP + WebSocket client used by the MCP server.

Responsibilities:
  - POST /prompt  (submit a workflow in API format)
  - Listen on /ws for execution events
  - GET /history/{prompt_id} to read final status
  - GET /view to resolve a saved output file
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.parse
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ComfyUIError(RuntimeError):
    pass


def queue_state_from(queue_payload: dict[str, Any], prompt_id: str) -> str | None:
    """Locate `prompt_id` in a ComfyUI /queue payload.

    Returns "running", "pending", or None. Split out as a free function so the
    mapping can be unit-tested without a live ComfyUI.

    Why this exists: /history only gets a prompt once it FINISHES, so asking
    history alone cannot tell "waiting behind other jobs" from "rendering right
    now" -- and those call for opposite reactions from whoever is watching. A
    stuck queue reported as "queued" is exactly how a jammed backlog hides.

    Entries look like [queue_index, prompt_id, workflow, extra, outputs]; this
    tolerates anything shaped differently rather than raising, because it runs
    while someone is already staring at something that looks broken.
    """
    for key, state in (("queue_running", "running"), ("queue_pending", "pending")):
        for entry in queue_payload.get(key) or []:
            try:
                if entry[1] == prompt_id:
                    return state
            except (IndexError, TypeError):
                continue
    return None


class ComfyUIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8188", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)

    # ---------- system ----------
    def health(self) -> dict[str, Any]:
        try:
            r = self._client.get("/system_stats")
            r.raise_for_status()
            return {"ok": True, **r.json()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def object_info(self, node_class: str | None = None) -> dict[str, Any]:
        url = "/object_info"
        if node_class:
            url += f"/{urllib.parse.quote(node_class)}"
        r = self._client.get(url)
        r.raise_for_status()
        return r.json()

    def get_history(self, prompt_id: str) -> dict[str, Any]:
        r = self._client.get(f"/history/{prompt_id}")
        r.raise_for_status()
        return r.json()

    def get_queue(self) -> dict[str, Any]:
        """The raw /queue payload: {"queue_running": [...], "queue_pending": [...]}."""
        r = self._client.get("/queue")
        r.raise_for_status()
        return r.json()

    def queue_state(self, prompt_id: str) -> str | None:
        """'running', 'pending', or None if the prompt is not in the queue."""
        try:
            return queue_state_from(self.get_queue(), prompt_id)
        except Exception:
            return None

    # ---------- prompt submission ----------
    def submit(self, workflow_api: dict[str, Any], client_id: str = "minimax-factory") -> str:
        payload = {"prompt": workflow_api, "client_id": client_id}
        r = self._client.post("/prompt", json=payload)
        if r.status_code != 200:
            raise ComfyUIError(f"POST /prompt -> {r.status_code}: {r.text[:500]}")
        data = r.json()
        if "error" in data and data.get("error"):
            raise ComfyUIError(f"ComfyUI rejected prompt: {json.dumps(data['error'])[:800]}")
        return data["prompt_id"]

    def upload_image(self, path: str, subfolder: str = "", overwrite: bool = True) -> str:
        """Upload an image into ComfyUI's input dir; returns the name to use in LoadImage.

        Going through /upload/image rather than writing into a bind-mounted
        directory keeps this working when the MCP server is not on the same
        host as ComfyUI -- which is a supported deployment here.

        ComfyUI may rename the file (it de-duplicates), so the returned name is
        the authoritative one and the caller must use it.
        """
        import os as _os

        if not _os.path.exists(path):
            raise ComfyUIError(f"image not found: {path}")
        with open(path, "rb") as fh:
            files = {"image": (_os.path.basename(path), fh, "application/octet-stream")}
            data = {"overwrite": "true" if overwrite else "false"}
            if subfolder:
                data["subfolder"] = subfolder
            r = self._client.post("/upload/image", files=files, data=data)
        if r.status_code != 200:
            raise ComfyUIError(f"POST /upload/image -> {r.status_code}: {r.text[:300]}")
        body = r.json()
        name = body.get("name")
        if not name:
            raise ComfyUIError(f"upload returned no name: {body}")
        sub = body.get("subfolder") or ""
        return f"{sub}/{name}" if sub else name

    def interrupt(self) -> None:
        self._client.post("/interrupt")

    # ---------- websocket monitoring ----------
    async def wait_for_execution(
        self,
        prompt_id: str,
        timeout: float = 1200.0,
        poll_interval: float = 3.0,
    ) -> dict[str, Any]:
        """Poll /history until the prompt completes or fails.

        Returns the history record for this prompt_id. Raises ComfyUIError on
        timeout or explicit execution error.
        """
        from websockets import ConnectionClosed
        from websockets.asyncio.client import connect

        ws_url = self.base_url.replace("http", "ws", 1) + "/ws?clientId=minimax-factory"
        deadline = asyncio.get_event_loop().time() + timeout

        async def _poll() -> dict[str, Any] | None:
            hist = self.get_history(prompt_id)
            rec = hist.get(prompt_id)
            if rec is None:
                return None
            status = rec.get("status", {})
            if status.get("completed") or rec.get("outputs"):
                return rec
            if status.get("status_str") == "error" or status.get("error"):
                raise ComfyUIError(f"Execution failed: {json.dumps(status)[:800]}")
            return None

        # Fast path: check immediately (might already be done or queued behind others)
        done = await _poll()
        if done:
            return done

        async with connect(ws_url) as ws:
            while asyncio.get_event_loop().time() < deadline:
                if done:
                    return done
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=poll_interval)
                except asyncio.TimeoutError:
                    done = await _poll()
                    continue
                except ConnectionClosed:
                    done = await _poll()
                    continue

                if isinstance(msg, bytes):
                    continue
                try:
                    evt = json.loads(msg)
                except json.JSONDecodeError:
                    continue

                evt_type = evt.get("type")
                if evt_type == "executing":
                    data = evt.get("data", {})
                    if data.get("prompt_id") == prompt_id and data.get("node") is None:
                        # finished executing this prompt
                        return await _poll()
                    if data.get("prompt_id") == prompt_id:
                        done = await _poll()
                        if done:
                            return done
                elif evt_type == "execution_error":
                    err = evt.get("data", {})
                    raise ComfyUIError(f"Execution error: {json.dumps(err)[:800]}")

                if done is None:
                    done = await _poll()

        raise ComfyUIError(f"Timed out after {timeout:.0f}s waiting for prompt {prompt_id}")

    # ---------- output resolution ----------
    def resolve_output(self, history_rec: dict[str, Any], output_dir: str) -> str | None:
        """Find the first saved .mp4 in outputs and return its absolute path."""
        outputs = history_rec.get("outputs", {})
        for out in outputs.values():
            # SaveVideo reports under "images" (with "animated": [true]); older
            # nodes use "videos"/"gifs". Scan every kind for a .mp4 filename.
            for items in out.values():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    fname = item.get("filename")
                    if fname and fname.endswith(".mp4"):
                        subdir = item.get("subfolder", "")
                        path = os.path.join(output_dir, subdir, fname)
                        if os.path.exists(path):
                            return path
        return None

    def download_file(self, filename: str, subfolder: str = "", dest_dir: str = ".",
                      file_type: str = "output") -> str:
        params = {"filename": filename, "type": file_type}
        if subfolder:
            params["subfolder"] = subfolder
        url = f"{self.base_url}/view?" + urllib.parse.urlencode(params)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, filename)
        with self._client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                f.writelines(resp.iter_bytes())
        return dest
