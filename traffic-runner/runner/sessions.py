"""Login sessions of the test accounts (messaging, social_post).

A session is a Playwright storage state (cookies + local storage, no passwords) captured once
by hand with scripts/capture_session.py, stored per device and platform:
    $RUNNER_SESSION_DIR/<device>.<platform>.json        storage state
    $RUNNER_SESSION_DIR/<device>.<platform>.meta.json   e.g. {"dm_url": ...} for Slack
On the gateway the folder is traffic-runner/sessions (root-only, not in git), mounted
read-only into the containers. Each block still starts in a fresh browser context: only the
login comes from the file, DNS and HTTP caches start empty.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .context import NotImplementedActivity


def session_dir() -> Path:
    return Path(os.environ.get("RUNNER_SESSION_DIR", "/app/sessions"))


def paths(device: str, platform: str, base: Path | None = None) -> tuple[Path, Path]:
    base = Path(base or session_dir())
    return base / f"{device}.{platform}.json", base / f"{device}.{platform}.meta.json"


def load(device: str, platform: str, base: Path | None = None) -> tuple[Path, dict]:
    """(storage state path, meta). NotImplementedActivity if no session was captured."""
    state, meta = paths(device, platform, base)
    if not state.is_file():
        raise NotImplementedActivity(
            f"no {platform} session for {device}: capture it with scripts/capture_session.py "
            f"--device {device} --platform {platform} (traffic-runner README, test accounts)")
    return state, (json.loads(meta.read_text()) if meta.is_file() else {})
