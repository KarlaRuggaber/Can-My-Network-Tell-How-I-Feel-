"""Per-day feature records (the app's ALL_DAILY table), computed one day per process.

Both pages (Early Signs, Network Metrics) read the same cache file
`feature_cache/features_<md5 of the selected dataset names>.csv`: one row per day with the base
record (`compute_daily_base_record`), the nine criteria's metric values and a `Fingerprint` of
the day's partition files. This module keeps that file up to date.

Memory: a day of a live persona has up to ~6 M rows. Computed in the long-running Streamlit
process, one day after another, the process kept growing (freed pandas/Arrow memory is not
returned to the system) until the kernel killed the app. Here each day runs in its own short
Python process, so its memory is returned when it exits, and the cache file is written after
every day (a crash or reload continues where it stopped). Only days whose partitions changed
(fingerprint) are recomputed.

Precompute from the command line, e.g. nightly or before a demo (run from app_pcap_to_dsm5/app):

    python -m metrics.daily_cache --dataset gw_mdd_suicidality_a
    python -m metrics.daily_cache --dataset gw_insomnia_a --processed-dir processed_parquet \\
        --cache-dir feature_cache [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pickle
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .base_features import compute_daily_base_record
from .common import drop_background, enrich_with_hostnames
from .criterion1 import Criterion1
from .criterion2 import Criterion2
from .criterion3 import Criterion3
from .criterion4 import Criterion4
from .criterion5 import Criterion5
from .criterion6 import Criterion6
from .criterion7 import Criterion7
from .criterion8 import Criterion8
from .criterion9 import Criterion9

APP_DIR = Path(__file__).resolve().parents[1]
PART_RE = re.compile(r"__(\d{8})_(\d{4})\.parquet$")
CRITERIA = (Criterion1, Criterion2, Criterion3, Criterion4, Criterion5, Criterion6, Criterion7, Criterion8, Criterion9)
EMPTY_DAY_COLUMNS = ["Timestamp", "Date", "Hour", "Protocol", "Source IP", "Destination IP", "Source Port",
                     "Destination Port", "Length", "IsDNS", "DNS_QNAME", "DNS_ANS_NAME", "DNS_ANS_IPS"]

Progress = Callable[[str], None]


# ------------------------------------------------------------------ partitions and cache paths

def partition_files(processed_dir: str | Path, base_name: str) -> list[str]:
    """All 5-min partition files of a dataset (not memoised: the live ingest adds files)."""
    d = os.path.join(processed_dir, base_name)
    if not os.path.isdir(d):
        return []
    return sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".parquet"))


def partition_start(path: str) -> datetime | None:
    """Start time from the file name pattern `__YYYYMMDD_HHMM.parquet`."""
    m = PART_RE.search(os.path.basename(path))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
    except ValueError:
        return None


def day_partition_files(processed_dir: str | Path, base_name: str, day) -> list[str]:
    day = pd.to_datetime(day).normalize()
    nxt = day + pd.Timedelta(days=1)
    out = []
    for p in partition_files(processed_dir, base_name):
        start = partition_start(p)
        if start is not None and day <= pd.Timestamp(start) < nxt:
            out.append(p)
    return out


def available_days(processed_dir: str | Path, base_names: Iterable[str]) -> list[pd.Timestamp]:
    days = set()
    for bn in base_names:
        for p in partition_files(processed_dir, bn):
            start = partition_start(p)
            if start is not None:
                days.add(pd.Timestamp(start.date()))
    return sorted(days)


def fingerprint_for_day(processed_dir: str | Path, base_names: Iterable[str], day) -> str:
    """md5 over the day's partition files (name|size|mtime): changes when the ingest adds or rewrites one."""
    parts = []
    for bn in base_names:
        for p in day_partition_files(processed_dir, bn, day):
            try:
                s = os.stat(p)
            except OSError:
                continue
            parts.append(f"{os.path.basename(p)}|{s.st_size}|{int(s.st_mtime)}")
    return hashlib.md5("|".join(sorted(parts)).encode("utf-8")).hexdigest()


def cache_key(base_names: Iterable[str]) -> str:
    return hashlib.md5("|".join(sorted(base_names)).encode("utf-8")).hexdigest()


def cache_path(cache_dir: str | Path, base_names: Iterable[str]) -> Path:
    return Path(cache_dir) / f"features_{cache_key(base_names)}.csv"


# ------------------------------------------------------------------ one day

# Columns the metrics read (plus Date for files without Timestamp). Leaving out Capture File,
# TCP Flags, DNS_QTYPE and the per-row Date objects saves about 40 % of a day's memory.
METRIC_COLUMNS = ["Timestamp", "Hour", "Protocol", "Source IP", "Destination IP", "Source Port",
                  "Destination Port", "Length", "IsDNS", "DNS_QNAME", "DNS_ANS_NAME", "DNS_ANS_IPS", "URL"]


def _columns_in(fp: str) -> list[str] | None:
    try:
        names = set(pq.read_schema(fp).names)
    except Exception:
        return None
    cols = [c for c in METRIC_COLUMNS if c in names]
    if "Timestamp" not in names and {"Date", "Hour"} <= names:
        cols.append("Date")
    return cols


def safe_read_parquet(fp: str, columns: list[str] | None = None) -> pd.DataFrame | None:
    """Read a partition (only `columns` if given); on errors keep the readable row groups."""
    try:
        return pd.read_parquet(fp, columns=columns)
    except Exception:
        try:
            pf = pq.ParquetFile(fp)
            subs = []
            for i in range(pf.num_row_groups):
                try:
                    subs.append(pf.read_row_group(i, columns=columns))
                except Exception:
                    continue
            if not subs:
                return None
            table = pa.concat_tables(subs, promote=True)
            try:
                return table.to_pandas(types_mapper=pd.ArrowDtype)
            except Exception:
                return table.to_pandas()
        except Exception:
            return None


def read_dataset_day(processed_dir: str | Path, base_name: str, day) -> pd.DataFrame:
    """One dataset's rows of a calendar day (local time), only the columns the metrics use."""
    day = pd.to_datetime(day).normalize()
    nxt = day + pd.Timedelta(days=1)
    frames = []
    for fp in day_partition_files(processed_dir, base_name, day):
        dfp = safe_read_parquet(fp, _columns_in(fp))
        if dfp is None:
            continue
        if "Timestamp" not in dfp.columns and {"Date", "Hour"}.issubset(dfp.columns):
            dfp["Timestamp"] = pd.to_datetime(dfp["Date"].astype(str)) + pd.to_timedelta(dfp["Hour"], unit="h")
        dfp["Timestamp"] = pd.to_datetime(dfp["Timestamp"], errors="coerce")
        frames.append(dfp)
    if not frames:
        return pd.DataFrame(columns=EMPTY_DAY_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    del frames  # each step replaces the previous table instead of keeping both
    in_day = (df["Timestamp"] >= day) & (df["Timestamp"] < nxt)
    if not in_day.all():  # partitions lie within the day, so this rarely copies
        df = df.loc[in_day]
    df = df.drop(columns=["Date"], errors="ignore")
    df["Hour"] = df["Timestamp"].dt.hour
    return df


def load_day(processed_dir: str | Path, base_names: Iterable[str], day) -> pd.DataFrame:
    """The selection's rows of a day, with hostnames and without machine background."""
    frames = [f for f in (read_dataset_day(processed_dir, bn, day) for bn in base_names) if not f.empty]
    if not frames:
        return pd.DataFrame(columns=EMPTY_DAY_COLUMNS)
    df = frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
    del frames
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = enrich_with_hostnames(df)  # rebinding frees the table without hostnames
    release_memory()
    return drop_background(df)


def compute_day_record(processed_dir: str | Path, base_names: list[str], day,
                       history_rows: list[dict] | None = None) -> dict | None:
    """Base record + every criterion's metric value for one day; None if the day has no rows.
    `history_rows` are the earlier days' records (for metrics against a baseline)."""
    df = load_day(processed_dir, base_names, day)
    release_memory()  # reading and concatenating leave large freed buffers behind
    if df.empty:
        return None
    rec = compute_daily_base_record(df)
    release_memory()
    rec["Date"] = pd.to_datetime(day).normalize()
    history = pd.DataFrame(history_rows or [])
    aux_ctx = dict(today_row=rec, ALL_DAILY=history)
    for cls in CRITERIA:
        try:
            metrics = cls().compute(df, rec, aux_ctx, history)
        except Exception:
            continue
        for m in metrics or []:
            col = m.get("dist_col")
            if col:
                rec[col] = m.get("value")
        release_memory()
    return rec


def release_memory() -> None:
    """Return freed memory to the system (Arrow's pool, glibc's heap); no-op where unsupported."""
    try:
        pa.default_memory_pool().release_unused()
    except Exception:
        pass
    if sys.platform.startswith("linux"):
        try:
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            pass


def compute_day_isolated(processed_dir: str | Path, base_names: list[str], day,
                         history_rows: list[dict] | None = None, timeout: float | None = None) -> dict | None:
    """compute_day_record in a fresh Python process, so its memory is returned when it exits."""
    with tempfile.TemporaryDirectory(prefix="daily_cache_") as tmp:
        hist_path, out_path = Path(tmp) / "history.pkl", Path(tmp) / "record.pkl"
        with open(hist_path, "wb") as f:
            pickle.dump(history_rows or [], f)
        env = dict(os.environ)
        env["PYTHONPATH"] = str(APP_DIR) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        cmd = [sys.executable, "-m", "metrics.daily_cache", "--child-day", pd.to_datetime(day).strftime("%Y-%m-%d"),
               "--processed-dir", str(processed_dir), "--history", str(hist_path), "--out", str(out_path)]
        for bn in base_names:
            cmd += ["--dataset", bn]
        proc = subprocess.run(cmd, cwd=str(APP_DIR), env=env, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
            raise RuntimeError(f"day {pd.to_datetime(day).date()} failed (exit {proc.returncode}): {' | '.join(tail)}")
        with open(out_path, "rb") as f:
            return pickle.load(f)


# ------------------------------------------------------------------ the cache file

def read_cache(path: str | Path) -> dict:
    """Existing cache rows by date (empty if missing or unreadable)."""
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        prev = pd.read_csv(path, parse_dates=["Date"])
    except Exception:
        return {}
    if "Date" not in prev.columns:
        return {}
    return {pd.to_datetime(r["Date"]).date(): r.to_dict() for _, r in prev.iterrows() if pd.notna(r["Date"])}


def write_cache(path: str | Path, rows_by_date: dict) -> None:
    """Write atomically, so a crash never leaves half a file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([rows_by_date[k] for k in sorted(rows_by_date)])
    tmp = path.with_suffix(f".tmp{os.getpid()}")
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def update_feature_cache(processed_dir: str | Path, cache_dir: str | Path, base_names: list[str],
                         days: Iterable | None = None, force: bool = False, isolate: bool = True,
                         progress: Progress | None = None) -> pd.DataFrame:
    """Bring the selection's cache file up to date and return the rows of `days` (all days if None).

    A day is recomputed when it is missing, its fingerprint changed, or `force`. Days are done in
    date order; each one gets the earlier days' rows as history. The file is written after every
    computed day.
    """
    base_names = sorted(base_names)
    path = cache_path(cache_dir, base_names)
    stored = read_cache(path)
    wanted = sorted({pd.to_datetime(d).normalize() for d in (days if days is not None else available_days(processed_dir, base_names))})
    say = progress or (lambda msg: None)
    rows: list[dict] = []
    todo = []
    for d in wanted:
        fp = fingerprint_for_day(processed_dir, base_names, d)
        old = stored.get(d.date())
        todo.append((d, fp, force or old is None or str(old.get("Fingerprint", "")) != fp))
    n_compute = sum(1 for *_, c in todo if c)
    done = 0
    for d, fp, needs in todo:
        if not needs:
            rows.append(stored[d.date()])
            continue
        done += 1
        say(f"Computing day {done} of {n_compute}: {d.date()}")
        t0 = time.monotonic()
        history = [dict(r) for r in rows]
        rec = (compute_day_isolated if isolate else compute_day_record)(processed_dir, base_names, d, history)
        if rec is None:
            stored.pop(d.date(), None)
            continue
        rec["Fingerprint"] = fp
        rows.append(rec)
        stored[d.date()] = rec
        write_cache(path, stored)
        say(f"  {d.date()} done in {time.monotonic() - t0:.0f} s")
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["Date"])
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    return out.sort_values("Date").reset_index(drop=True)


# ------------------------------------------------------------------ command line

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", action="append", required=True,
                   help="dataset (one person, e.g. gw_insomnia_a); repeat to combine several into one selection")
    p.add_argument("--processed-dir", default=str(APP_DIR / "processed_parquet"))
    p.add_argument("--cache-dir", default=str(APP_DIR / "feature_cache"))
    p.add_argument("--day", action="append", help="only this day (YYYY-MM-DD), repeatable; default: all days")
    p.add_argument("--force", action="store_true", help="recompute even unchanged days")
    p.add_argument("--in-process", action="store_true", help="no child process per day (needs more memory)")
    # internal: one day in a child process (compute_day_isolated)
    p.add_argument("--child-day", help=argparse.SUPPRESS)
    p.add_argument("--history", help=argparse.SUPPRESS)
    p.add_argument("--out", help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    if args.child_day:
        with open(args.history, "rb") as f:
            history = pickle.load(f)
        rec = compute_day_record(args.processed_dir, args.dataset, args.child_day, history)
        with open(args.out, "wb") as f:
            pickle.dump(rec, f)
        return 0

    df = update_feature_cache(args.processed_dir, args.cache_dir, args.dataset, args.day, args.force,
                              isolate=not args.in_process, progress=lambda m: print(m, flush=True))
    print(f"{len(df)} day(s) in {cache_path(args.cache_dir, sorted(args.dataset))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
