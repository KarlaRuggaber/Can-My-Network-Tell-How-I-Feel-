"""Partition files per dataset and day, with a signature that changes when a file is added or rewritten."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

_NAME = re.compile(r"__(\d{8})_(\d{4})\.parquet$")


def partition_start(path: Path) -> datetime | None:
    """Start of a 5-minute partition from its file name (same rule as the Streamlit app)."""
    m = _NAME.search(path.name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
    except ValueError:
        return None


def list_datasets(processed_dir: Path) -> list[str]:
    if not processed_dir.is_dir():
        return []
    return sorted(p.name for p in processed_dir.iterdir() if p.is_dir() and any(p.glob("*.parquet")))


def partitions_by_day(processed_dir: Path, dataset: str) -> dict[date, list[Path]]:
    """Partition files grouped by the calendar day of their start time, sorted."""
    out: dict[date, list[Path]] = defaultdict(list)
    d = processed_dir / dataset
    if not d.is_dir():
        return {}
    for p in d.glob("*.parquet"):
        start = partition_start(p)
        if start is not None:
            out[start.date()].append(p)
    return {k: sorted(v) for k, v in sorted(out.items())}


def day_signature(files: list[Path]) -> str:
    parts = []
    for p in files:
        try:
            st = p.stat()
            parts.append(f"{p.name}|{st.st_size}|{st.st_mtime_ns}")
        except OSError:
            parts.append(f"{p.name}|missing")
    return hashlib.md5("\n".join(parts).encode()).hexdigest()
