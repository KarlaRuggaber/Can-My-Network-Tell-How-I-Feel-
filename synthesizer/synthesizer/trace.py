"""Ingested Parquet rows -> block_id, via segments.csv (README §7). Needs pandas + pyarrow (like the app).

A row belongs to the segment of its client IP that contains its time. The ingest stores naive Europe/Zurich time;
in the hour that occurs twice at the end of summer time the instant is ambiguous, those rows are counted apart.
"""

from __future__ import annotations

import bisect
import csv
from pathlib import Path

from .catalog import S

EDGE_US = 2   # float timestamps in the ingest (datetime.fromtimestamp(float)) may be off by a microsecond


def trace(synth_dir: str | Path, parquet_dir: str | Path) -> tuple[list[dict], dict]:
    import pandas as pd

    synth_dir = Path(synth_dir)
    with open(synth_dir / "segments.csv", newline="", encoding="utf-8") as f:
        segs = list(csv.DictReader(f))
    with open(synth_dir / "manifest.csv", newline="", encoding="utf-8") as f:
        manifest = {r["block_id"]: r for r in csv.DictReader(f)}
    by_ip: dict[str, list[tuple[int, int, str]]] = {}
    for s in segs:
        by_ip.setdefault(s["ip"], []).append((int(s["t_from_us"]), int(s["t_to_us"]), s["block_ids"].split(";")[0]))
    starts = {}
    for ip, lst in by_ip.items():
        lst.sort()
        starts[ip] = [x[0] for x in lst]

    files = sorted(Path(parquet_dir).glob("*.parquet"))
    if not files:
        raise ValueError(f"{parquet_dir}: no Parquet files")
    df = pd.concat([pd.read_parquet(p, columns=["Timestamp", "Source IP", "Destination IP"]) for p in files],
                   ignore_index=True)
    local = pd.to_datetime(df["Timestamp"]).dt.tz_localize("Europe/Zurich", ambiguous="NaT", nonexistent="NaT")
    epoch_us = (local.dt.tz_convert("UTC") - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(microseconds=1)

    counts: dict[str, int] = {}
    stats = {"rows": len(df), "untraced": 0, "dst_ambiguous": 0}
    for t, src, dst in zip(epoch_us.tolist(), df["Source IP"].tolist(), df["Destination IP"].tolist()):
        if t is None or t != t:   # NaT
            stats["dst_ambiguous"] += 1
            continue
        t = int(t)
        ip = src if src in by_ip else (dst if dst in by_ip else None)
        block = None
        if ip is not None:
            lst = by_ip[ip]
            j = bisect.bisect_right(starts[ip], t + EDGE_US) - 1
            while j >= 0 and lst[j][0] > t - 12 * 3600 * S:   # overlapping segments (companion overlay): any that contains t
                if lst[j][0] - EDGE_US <= t <= lst[j][1] + EDGE_US:
                    block = lst[j][2]
                    break
                j -= 1
        if block is None:
            stats["untraced"] += 1
        else:
            counts[block] = counts.get(block, 0) + 1

    rows = []
    for block_id, m in manifest.items():
        if m["packets"] == "" and not counts.get(block_id):
            continue
        expected = int(m["packets"] or 0)
        got = counts.get(block_id, 0)
        rows.append({"block_id": block_id, "activity_id": m["activity_id"], "manifest_packets": expected,
                     "parquet_rows": got, "missing": expected - got})
    return rows, stats
