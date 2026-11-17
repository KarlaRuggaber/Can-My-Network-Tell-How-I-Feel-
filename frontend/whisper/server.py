"""Local speech-to-text for the results portal: faster-whisper behind a small HTTP API.

Runs on the same machine as the portal (127.0.0.1:8601) and is reached only through the portal's
/api/transcribe, which checks the login. Audio never leaves the machine and is not stored: each
recording is decoded in memory, transcribed and dropped. No API key, no external service; the model
is downloaded once (Hugging Face, Systran/faster-whisper-*) into WHISPER_CACHE.

    WHISPER_MODEL=small            # tiny, base, small, medium, large-v3, distil-large-v3, or a local path
    WHISPER_COMPUTE=int8           # int8 on the CPU keeps "small" well below 1 GB of RAM
    WHISPER_THREADS=2              # CPU threads (leave room for the capture on the gateway)
    WHISPER_BEAM=5                 # beam size (1 is faster, 5 more accurate)
    WHISPER_LANGUAGE=              # empty: detect per recording; or "en", "de", ...
    WHISPER_IDLE_UNLOAD=600        # seconds without a request before the model is unloaded (0: never)
    WHISPER_PRELOAD=0              # 1: load (and download) the model at start instead of on first use
    WHISPER_CACHE=~/.cache/cmn-whisper
    WHISPER_MAX_SECONDS=300        # longer recordings are refused

    uvicorn server:app --host 127.0.0.1 --port 8601
"""

from __future__ import annotations

import gc
import io
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request

MODEL = os.environ.get("WHISPER_MODEL", "small")
COMPUTE = os.environ.get("WHISPER_COMPUTE", "int8")
THREADS = int(os.environ.get("WHISPER_THREADS", "2"))
BEAM = int(os.environ.get("WHISPER_BEAM", "5"))
LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "").strip() or None
IDLE_UNLOAD = int(os.environ.get("WHISPER_IDLE_UNLOAD", "600"))
CACHE = Path(os.environ.get("WHISPER_CACHE", "~/.cache/cmn-whisper")).expanduser()
MAX_SECONDS = int(os.environ.get("WHISPER_MAX_SECONDS", "300"))
MAX_BYTES = 25 * 1024 * 1024

log = logging.getLogger("whisper")
_lock = threading.Lock()          # one transcription at a time: it is CPU-bound
_model: Any = None
_last_use = 0.0


def _get_model() -> Any:
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        t = time.time()
        _model = WhisperModel(MODEL, device="cpu", compute_type=COMPUTE, cpu_threads=THREADS,
                              download_root=str(CACHE))
        log.warning("loaded %s (%s) in %.1f s", MODEL, COMPUTE, time.time() - t)
    return _model


def _unloader() -> None:
    global _model
    while True:
        time.sleep(30)
        if IDLE_UNLOAD and _model is not None and time.time() - _last_use > IDLE_UNLOAD:
            with _lock:
                if _model is not None and time.time() - _last_use > IDLE_UNLOAD:
                    _model = None
                    gc.collect()
                    log.warning("unloaded %s after %d s idle", MODEL, IDLE_UNLOAD)


app = FastAPI(title="cmn-whisper", docs_url=None, redoc_url=None)


@app.on_event("startup")
def _start() -> None:
    global _last_use
    threading.Thread(target=_unloader, daemon=True).start()
    if os.environ.get("WHISPER_PRELOAD", "") in ("1", "true", "yes"):
        def preload() -> None:
            global _last_use
            with _lock:
                _get_model()
                _last_use = time.time()
        threading.Thread(target=preload, daemon=True).start()


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "model": MODEL, "compute": COMPUTE, "loaded": _model is not None,
            "language": LANGUAGE, "max_seconds": MAX_SECONDS}


@app.post("/transcribe")
async def transcribe(request: Request, language: str | None = None) -> dict[str, Any]:
    audio = await request.body()
    if not audio:
        raise HTTPException(400, "no audio")
    if len(audio) > MAX_BYTES:
        raise HTTPException(413, "recording too large")
    lang = (language or LANGUAGE or "").strip().lower() or None
    if lang and not (2 <= len(lang) <= 3 and lang.isalpha()):
        raise HTTPException(422, "language must be a code such as en or de")
    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(_run, audio, lang)


def decode(audio: bytes) -> Any:
    """Any recording a browser makes (WebM/Opus, Ogg, MP4/AAC, WAV) as 16 kHz mono float32 samples."""
    import av
    import numpy as np
    parts = []
    with av.open(io.BytesIO(audio), mode="r") as container:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in container.decode(audio=0):
            parts += [f.to_ndarray().reshape(-1) for f in resampler.resample(frame)]
        parts += [f.to_ndarray().reshape(-1) for f in resampler.resample(None)]
    if not parts:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(parts).astype(np.float32) / 32768.0


def _run(audio: bytes, lang: str | None) -> dict[str, Any]:
    global _last_use
    try:
        samples = decode(audio)
    except Exception:  # noqa: BLE001 - any decoder error means the upload is not usable audio
        raise HTTPException(415, "could not read the recording")
    if len(samples) < 16000 * 0.3:
        return {"text": "", "language": None, "language_probability": 0, "seconds": round(len(samples) / 16000, 1),
                "took": 0, "model": MODEL}
    seconds = len(samples) / 16000
    if seconds > MAX_SECONDS:
        raise HTTPException(413, f"recording longer than {MAX_SECONDS // 60} minutes")
    with _lock:
        t = time.time()
        model = _get_model()
        segments, info = model.transcribe(samples, language=lang, beam_size=BEAM, vad_filter=True,
                                          condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segments).strip()
        _last_use = time.time()
    return {"text": text, "language": info.language, "language_probability": round(info.language_probability, 3),
            "seconds": round(seconds, 1), "took": round(time.time() - t, 1), "model": MODEL}
