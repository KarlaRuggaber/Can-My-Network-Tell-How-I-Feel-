"""Speech to text through the local Whisper service (frontend/whisper/server.py).

The browser records a short clip; the portal checks the login and passes it to the Whisper service
on the same machine, which returns the text. The audio never leaves the machine and is not stored,
and no API key is involved.

    CMN_WHISPER_URL=http://127.0.0.1:8601    # default; "off" turns dictation off
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

DEFAULT_URL = "http://127.0.0.1:8601"
MAX_AUDIO_BYTES = 25 * 1024 * 1024
STATUS_SECONDS = 30            # how long a health check result is reused


class SpeechError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Speech:
    def __init__(self, url: str | None = None, transport: httpx.AsyncBaseTransport | None = None):
        url = os.environ.get("CMN_WHISPER_URL", DEFAULT_URL) if url is None else url
        self.url = "" if url.strip().lower() in ("", "off", "0", "no") else url.rstrip("/")
        self.transport = transport
        self._status: tuple[float, dict[str, Any]] | None = None

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, timeout=timeout)

    async def status(self) -> dict[str, Any]:
        if not self.url:
            return {"available": False}
        if self._status and time.time() - self._status[0] < STATUS_SECONDS:
            return self._status[1]
        try:
            async with self._client(2.0) as c:
                r = await c.get(f"{self.url}/health")
            h = r.json() if r.status_code == 200 else {}
            st = {"available": bool(h.get("ok")), "max_seconds": h.get("max_seconds", 300)}
        except (httpx.HTTPError, ValueError):
            st = {"available": False}
        self._status = (time.time(), st)
        return st

    async def transcribe(self, audio: bytes, content_type: str) -> dict[str, Any]:
        if not self.url:
            raise SpeechError(503, "Dictation is turned off on this server.")
        try:
            async with self._client(180.0) as c:
                r = await c.post(f"{self.url}/transcribe", content=audio,
                                 headers={"content-type": content_type or "application/octet-stream"})
        except httpx.TimeoutException:
            raise SpeechError(504, "Turning the recording into text took too long. Try a shorter one.")
        except httpx.HTTPError:
            self._status = None
            raise SpeechError(503, "The speech-to-text service is not running.")
        if r.status_code != 200:
            try:
                detail = r.json().get("detail", "")
            except ValueError:
                detail = ""
            raise SpeechError(422 if r.status_code in (400, 413, 415, 422) else 502,
                              f"Could not turn the recording into text{': ' + detail if detail else ''}.")
        d = r.json()
        return {"text": str(d.get("text", "")).strip(), "language": d.get("language"),
                "seconds": d.get("seconds")}
