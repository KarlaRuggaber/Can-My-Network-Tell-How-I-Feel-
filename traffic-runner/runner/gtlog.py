"""Ground-truth log: one CSV row per executed activity (activity catalog §1).

Several containers append to the same file on the shared /logs volume, so every write
holds an exclusive flock on the file.
"""

from __future__ import annotations

import csv
import fcntl
import io
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FIELDS = ["start", "end", "device", "activity_id", "domains", "profile", "seed", "block_id", "status"]
STATUSES = ("ok", "error", "not_implemented")
LOG_NAME = "ground_truth.csv"
DEFAULT_TZ = "Europe/Zurich"


def log_path() -> Path:
    return Path(os.environ.get("RUNNER_LOG_DIR", "/logs")) / LOG_NAME


def local_tz() -> ZoneInfo:
    try:
        return ZoneInfo(os.environ.get("TZ") or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def now_iso() -> str:
    """Current local time, ISO-8601 with UTC offset, e.g. 2026-10-16T16:48:59+02:00."""
    return datetime.now(local_tz()).isoformat(timespec="seconds")


def append(row: dict, path: Path | None = None) -> None:
    """Append one row; writes the header if the file is new. Safe across processes."""
    if set(row) != set(FIELDS):
        raise ValueError(f"row fields {sorted(row)} != {FIELDS}")
    if row["status"] not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    path = Path(path or log_path())
    path.parent.mkdir(parents=True, exist_ok=True)

    buf = io.StringIO()
    csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n").writerow(row)

    with open(path, "a+", newline="", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            first = f.readline()
            if not first:
                f.write(",".join(FIELDS) + "\n")
            elif first.rstrip("\r\n") != ",".join(FIELDS):
                raise RuntimeError(f"{path} has an unexpected header: {first.strip()!r}")
            f.write(buf.getvalue())  # "a+" always appends at the end
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
