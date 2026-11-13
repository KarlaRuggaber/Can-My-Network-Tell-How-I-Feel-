"""On-disk cache of per-day results: <cache_dir>/<dataset>/<YYYY-MM-DD>.json.

A day is recomputed when its partition files change (signature), when the metric code changes
(code version), or when an earlier day was recomputed (history-dependent metrics such as the
30-day sleep z-score read the previous rows).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from . import daily


def code_version(app_dir: Path) -> str:
    """Hash of the metric code (thesis app) and of this package's day computation."""
    h = hashlib.md5()
    files = sorted((Path(app_dir) / "metrics").glob("*.py")) + [Path(daily.__file__)]
    for p in files:
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


class DayStore:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)

    def path(self, dataset: str, day: date) -> Path:
        return self.cache_dir / dataset / f"{day.isoformat()}.json"

    def load(self, dataset: str, day: date) -> dict[str, Any] | None:
        p = self.path(dataset, day)
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save(self, dataset: str, day: date, record: dict[str, Any]) -> None:
        p = self.path(dataset, day)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(record, f, separators=(",", ":"))
        os.replace(tmp, p)

    def datasets(self) -> list[str]:
        if not self.cache_dir.is_dir():
            return []
        return sorted(p.name for p in self.cache_dir.iterdir() if p.is_dir() and any(p.glob("*.json")))

    def days(self, dataset: str) -> Iterator[tuple[date, dict[str, Any]]]:
        d = self.cache_dir / dataset
        if not d.is_dir():
            return
        for p in sorted(d.glob("*.json")):
            try:
                day = date.fromisoformat(p.stem)
                yield day, json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue


def history_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Previous metric rows as the ALL_DAILY history DataFrame the criteria expect."""
    if not records:
        return pd.DataFrame(columns=["Date"])
    df = pd.DataFrame([r["metrics"] for r in records])
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df.sort_values("Date").reset_index(drop=True)
