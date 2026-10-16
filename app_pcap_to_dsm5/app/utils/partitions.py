"""Cheap change detection for processed_parquet datasets.

Lets the pages notice partitions that the live ingest service (ingest/tapingest.py)
adds or rewrites while the app is running.
"""

from __future__ import annotations

import hashlib
import os


def dataset_signature(processed_dir, base_names) -> str:
    """Cheap fingerprint of the partition files of the given datasets (count + newest mtime).
    Changes whenever a partition is added or rewritten, e.g. by the live ingest service."""
    parts = []
    for bn in sorted(base_names):
        d = os.path.join(processed_dir, bn)
        n, newest = 0, 0.0
        try:
            with os.scandir(d) as it:
                for e in it:
                    if e.name.endswith(".parquet"):
                        n += 1
                        try: newest = max(newest, e.stat().st_mtime)
                        except OSError: pass
        except OSError:
            pass
        parts.append(f"{bn}|{n}|{newest:.3f}")
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def newest_partition_mtime(processed_dir, base_names) -> float:
    newest = 0.0
    for bn in base_names:
        try:
            with os.scandir(os.path.join(processed_dir, bn)) as it:
                for e in it:
                    if e.name.endswith(".parquet"):
                        try: newest = max(newest, e.stat().st_mtime)
                        except OSError: pass
        except OSError:
            pass
    return newest
