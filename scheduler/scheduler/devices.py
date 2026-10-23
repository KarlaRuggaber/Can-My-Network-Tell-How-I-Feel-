"""Read traffic-runner/config/devices.csv and map a dataset's roles to device names.

The file is shared with the runner and the ingest (traffic-runner/README.md §5): header
`device,role,mac,ip,dataset`, lines starting with `#` are comments. The scheduler only reads it.
"""

from __future__ import annotations

import csv
from pathlib import Path

COLUMNS = ["device", "role", "mac", "ip", "dataset"]


class DeviceError(ValueError):
    pass


def load(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    with open(path, newline="", encoding="utf-8") as f:
        lines = [line for line in f.read().splitlines() if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader(lines)
    if reader.fieldnames != COLUMNS:
        raise DeviceError(f"{path}: header must be {','.join(COLUMNS)}, got {reader.fieldnames}")
    rows = []
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise DeviceError(f"{path}: row {row} does not have {len(COLUMNS)} columns")
        rows.append({k: v.strip() for k, v in row.items()})
    return rows


def map_roles(rows: list[dict[str, str]], dataset: str, roles: list[str]) -> dict[str, str]:
    """role -> device name for `dataset`. Every role must exist exactly once."""
    mine = [r for r in rows if r["dataset"] == dataset]
    if not mine:
        known = sorted({r["dataset"] for r in rows})
        raise DeviceError(f"dataset '{dataset}' not in devices.csv (known: {', '.join(known) or 'none'})")
    out: dict[str, str] = {}
    for role in roles:
        hits = [r["device"] for r in mine if r["role"] == role]
        if len(hits) != 1:
            raise DeviceError(f"dataset '{dataset}' needs exactly one '{role}' device in devices.csv, found {hits}")
        out[role] = hits[0]
    return out
