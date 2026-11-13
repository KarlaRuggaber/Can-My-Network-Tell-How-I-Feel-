"""Daily metrics per dataset, computed with the unchanged metric code of the thesis app.

Mirrors compute_all_daily() and _load_day_dataframe_cached() of
app/pages/01_Early_Signs_Overview.py, but processes one day at a time and keeps only the
resulting metric row, so memory stays at roughly one day of packets (~1-2 GB) instead of the
Streamlit app's cache of every day's DataFrame.
"""

from __future__ import annotations

import functools
import gc
import importlib
import math
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

# Columns the metric code reads; the rest of a partition (e.g. Capture File) is not loaded.
_ACTIVITY_BIN_MIN = 5


@dataclass
class MetricCode:
    """Handles to the thesis app's metric code, imported from app_dir."""
    compute_daily_base_record: Callable[[pd.DataFrame], dict]
    enrich_with_hostnames: Callable[[pd.DataFrame], pd.DataFrame]
    drop_background: Callable[[pd.DataFrame], pd.DataFrame]
    criteria: tuple[Any, ...]
    labels: dict[str, str]          # dist_col -> label from the criterion definitions
    criterion_of: dict[str, str]    # dist_col -> "C1".."C9"


def _memoize_is_private_ip(modules: list[Any]) -> None:
    """Cache metrics.common.is_private_ip, a pure function of the IP string.

    The metric code calls it per packet inside row-wise DataFrame.apply (is_outbound/is_inbound),
    which is ~85 % of the run time on a busy day, while a day has only a few hundred distinct IPs.
    Results are unchanged (tests/test_export_api.py::test_ip_cache_does_not_change_results); the
    metric code itself is not modified, only the function object in the loaded modules is swapped.
    Disable with CMN_NO_IP_CACHE=1.
    """
    common = next(m for m in modules if m.__name__ == "metrics.common")
    original = getattr(common.is_private_ip, "__wrapped_original__", common.is_private_ip)
    cached_fn = functools.lru_cache(maxsize=1 << 16)(original)

    def is_private_ip(ip_str):
        try:
            return cached_fn(ip_str)
        except TypeError:  # unhashable input: fall back to the original
            return original(ip_str)

    is_private_ip.__wrapped_original__ = original  # type: ignore[attr-defined]
    for m in modules:
        if getattr(m, "is_private_ip", None) in (original, common.is_private_ip):
            m.is_private_ip = is_private_ip


def _restore_is_private_ip(modules: list[Any]) -> None:
    for m in modules:
        f = getattr(m, "is_private_ip", None)
        if f is not None and hasattr(f, "__wrapped_original__"):
            m.is_private_ip = f.__wrapped_original__


def load_metric_code(app_dir: Path, ip_cache: bool | None = None) -> MetricCode:
    app_dir = Path(app_dir).resolve()
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    base = importlib.import_module("metrics.base_features")
    common = importlib.import_module("metrics.common")
    criteria, labels, criterion_of = [], {}, {}
    modules: list[Any] = [common, base]
    for i in range(1, 10):
        mod = importlib.import_module(f"metrics.criterion{i}")
        modules.append(mod)
        criteria.append(getattr(mod, f"Criterion{i}")())
        for d in getattr(mod, f"C{i}_DEFS", []):
            labels[d.dist_col] = d.label
            criterion_of[d.dist_col] = f"C{i}"
    if ip_cache is None:
        ip_cache = os.environ.get("CMN_NO_IP_CACHE", "") not in ("1", "true", "yes")
    (_memoize_is_private_ip if ip_cache else _restore_is_private_ip)(modules)
    return MetricCode(
        compute_daily_base_record=base.compute_daily_base_record,
        enrich_with_hostnames=common.enrich_with_hostnames,
        drop_background=common.drop_background,
        criteria=tuple(criteria),
        labels=labels,
        criterion_of=criterion_of,
    )


def read_partitions(files: list[Path]) -> pd.DataFrame:
    frames = []
    for fp in files:
        try:
            frames.append(pd.read_parquet(fp))
        except Exception:
            continue  # same as the page: unreadable partitions are skipped
    if not frames:
        return pd.DataFrame(columns=["Timestamp"])
    return pd.concat(frames, ignore_index=True)


def prepare_day(df: pd.DataFrame, day: date, code: MetricCode) -> pd.DataFrame:
    """Timestamp normalisation, day filter, hostname enrichment, background removal (as the page)."""
    if df.empty:
        return df
    df = df.copy()
    if "Timestamp" not in df.columns and {"Date", "Hour"}.issubset(df.columns):
        df["Timestamp"] = pd.to_datetime(df["Date"].astype(str)) + pd.to_timedelta(df["Hour"], unit="h")
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    start = pd.Timestamp(day)
    df = df[(df["Timestamp"] >= start) & (df["Timestamp"] < start + pd.Timedelta(days=1))].copy()
    df["Date"] = df["Timestamp"].dt.date
    df["Hour"] = df["Timestamp"].dt.hour
    df = code.drop_background(code.enrich_with_hostnames(df))
    df = df.dropna(subset=["Timestamp"]).sort_values("Timestamp")
    return df


def compute_metric_row(df_day: pd.DataFrame, day: date, history: pd.DataFrame,
                       code: MetricCode) -> dict[str, Any]:
    """One ALL_DAILY row: base record plus every criterion metric (dist_col -> value)."""
    today = code.compute_daily_base_record(df_day)
    today["Date"] = pd.Timestamp(day).normalize()
    aux_ctx = {
        "today_row": today,
        "ALL_DAILY": history,
        "IS_val": today.get("IS"),
        "IV_val": today.get("IV"),
        "nd_ratio": today.get("ND_Ratio"),
        "n_total_packets_today": today.get("n_total_packets_today"),
        "n_night_packets_today": today.get("n_night_packets_today"),
        "night_pkts_today": today.get("night_pkts_today"),
        "day_pkts_today": today.get("day_pkts_today"),
        "down_bytes_today": today.get("down_bytes_today"),
        "up_bytes_today": today.get("up_bytes_today"),
    }
    for crit in code.criteria:
        try:
            metrics = crit.compute(df_day, today, aux_ctx, history)
        except Exception:
            continue
        for m in metrics or []:
            if m.get("dist_col"):
                today[m["dist_col"]] = m.get("value")
    return today


def activity_bins(df_day: pd.DataFrame, day: date, ip_to_device: dict[str, str]) -> dict[str, Any]:
    """Packets per 5-minute bin over the day, total and per simulated device (by local IP)."""
    n_bins = 24 * 60 // _ACTIVITY_BIN_MIN
    out: dict[str, Any] = {"bin_minutes": _ACTIVITY_BIN_MIN, "total": [0] * n_bins, "devices": {}}
    if df_day.empty:
        return out
    minute = (df_day["Timestamp"] - pd.Timestamp(day)).dt.total_seconds() // 60
    b = (minute // _ACTIVITY_BIN_MIN).clip(0, n_bins - 1).astype(int)
    out["total"] = np.bincount(b, minlength=n_bins).astype(int).tolist()
    for col in ("Source IP", "Destination IP"):
        if col not in df_day.columns:
            return out
    for ip, dev in ip_to_device.items():
        mask = (df_day["Source IP"] == ip) | (df_day["Destination IP"] == ip)
        if mask.any():
            out["devices"][dev] = np.bincount(b[mask], minlength=n_bins).astype(int).tolist()
    return out


def json_safe(row: dict[str, Any]) -> dict[str, Any]:
    """Scalar metric values only; NaN/inf -> None, timestamps -> ISO strings."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (pd.Timestamp, datetime, date)):
            out[k] = pd.Timestamp(v).isoformat()
        elif isinstance(v, (bool, np.bool_)):
            out[k] = bool(v)
        elif isinstance(v, (int, np.integer)):
            out[k] = int(v)
        elif isinstance(v, (float, np.floating)):
            f = float(v)
            out[k] = f if math.isfinite(f) else None
        elif v is None or isinstance(v, str):
            out[k] = v
        # lists, dicts, Series: not part of the daily metric table
    return out


def compute_day(files: list[Path], day: date, history: pd.DataFrame, code: MetricCode,
                ip_to_device: dict[str, str]) -> dict[str, Any]:
    raw = read_partitions(files)
    n_raw = int(len(raw))
    df_day = prepare_day(raw, day, code)
    del raw
    if df_day.empty:
        row: dict[str, Any] = {"Date": pd.Timestamp(day)}
        bins = activity_bins(df_day, day, ip_to_device)
        first = last = None
    else:
        row = compute_metric_row(df_day, day, history, code)
        bins = activity_bins(df_day, day, ip_to_device)
        first = df_day["Timestamp"].iloc[0].isoformat()
        last = df_day["Timestamp"].iloc[-1].isoformat()
    n_kept = int(len(df_day))
    del df_day
    gc.collect()
    return {
        "metrics": json_safe(row),
        "activity": bins,
        "packets_raw": n_raw,
        "packets_kept": n_kept,
        "first_packet": first,
        "last_packet": last,
    }


def day_end(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time()) + timedelta(days=1)
