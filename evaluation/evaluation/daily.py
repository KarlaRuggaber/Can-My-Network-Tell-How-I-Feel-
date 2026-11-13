"""Daily metrics per dataset, computed exactly like the app's Early Signs page (`compute_all_daily` in
`app_pcap_to_dsm5/app/pages/01_Early_Signs_Overview.py`), but one day at a time and without Streamlit's cache.

The page keeps every loaded day in `st.cache_data` (up to 256 entries), so four weeks of three personas need
more than 20 GB. Here a day is loaded, computed and released before the next one, which keeps memory at the size
of one day. The metric code itself is the app's (`metrics/`), imported unchanged.

Per dataset and day the result is the page's `today` row: the base record (`compute_daily_base_record`) plus every
criterion metric under its `dist_col`, with the days before it as history (`ALL_DAILY`), as on the page.
"""

from __future__ import annotations

import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).resolve().parents[2] / "app_pcap_to_dsm5" / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from metrics.base_features import compute_daily_base_record  # noqa: E402
from metrics.common import drop_background, enrich_with_hostnames  # noqa: E402
from metrics.criterion1 import Criterion1  # noqa: E402
from metrics.criterion2 import Criterion2  # noqa: E402
from metrics.criterion3 import Criterion3  # noqa: E402
from metrics.criterion4 import Criterion4  # noqa: E402
from metrics.criterion5 import Criterion5  # noqa: E402
from metrics.criterion6 import Criterion6  # noqa: E402
from metrics.criterion7 import Criterion7  # noqa: E402
from metrics.criterion8 import Criterion8  # noqa: E402
from metrics.criterion9 import Criterion9  # noqa: E402

# Same classes and order as CRITERION_CLASSES on the page.
CRITERIA = (Criterion1, Criterion2, Criterion3, Criterion4, Criterion5, Criterion6, Criterion7, Criterion8,
            Criterion9)
_PARTITION_RE = re.compile(r"__(\d{8})_(\d{4})\.parquet$")
AUX_KEYS = {"IS_val": "IS", "IV_val": "IV", "nd_ratio": "ND_Ratio", "n_total_packets_today": "n_total_packets_today",
            "n_night_packets_today": "n_night_packets_today", "night_pkts_today": "night_pkts_today",
            "day_pkts_today": "day_pkts_today", "down_bytes_today": "down_bytes_today",
            "up_bytes_today": "up_bytes_today"}


def partitions_by_day(dataset_dir: Path) -> dict[date, list[Path]]:
    """Partition files grouped by the (naive local) day of their start, as `load_day_dataframe` selects them."""
    out: dict[date, list[Path]] = {}
    for p in sorted(Path(dataset_dir).glob("*.parquet")):
        m = _PARTITION_RE.search(p.name)
        if m:
            start = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
            out.setdefault(start.date(), []).append(p)
    return out


def load_day(files: list[Path], day: date) -> pd.DataFrame:
    """The page's `_load_day_dataframe_cached`: read, derive Timestamp, keep the day, add hostnames, drop background."""
    frames = []
    for fp in files:
        df = pd.read_parquet(fp)
        if "Timestamp" not in df.columns and {"Date", "Hour"}.issubset(df.columns):
            df["Timestamp"] = pd.to_datetime(df["Date"].astype(str)) + pd.to_timedelta(df["Hour"], unit="h")
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["Timestamp"])
    out = pd.concat(frames, ignore_index=True)
    lo = pd.Timestamp(day)
    out = out[(out["Timestamp"] >= lo) & (out["Timestamp"] < lo + pd.Timedelta(days=1))].copy()
    out["Date"] = out["Timestamp"].dt.date
    out["Hour"] = out["Timestamp"].dt.hour
    out = drop_background(enrich_with_hostnames(out))
    out = out.dropna(subset=["Timestamp"]).sort_values("Timestamp")
    return out


def compute_dataset(dataset_dir: Path, days: list[date] | None = None, log=print) -> tuple[pd.DataFrame, dict]:
    """All days of one dataset (or `days`), in order, each with the previous days as history.

    Returns the daily table and per-criterion error counts. The page silently skips a criterion that raises;
    here it is skipped the same way, but counted."""
    by_day = partitions_by_day(dataset_dir)
    wanted = sorted(set(days) & set(by_day)) if days else sorted(by_day)
    criteria = [cls() for cls in CRITERIA]
    rows: list[dict] = []
    errors: dict[str, int] = {}
    for d in wanted:
        t0 = time.time()
        df_day = load_day(by_day[d], d)
        if df_day.empty:
            continue
        today = compute_daily_base_record(df_day)
        today["Date"] = pd.Timestamp(d)
        history = pd.DataFrame(rows).sort_values("Date") if rows else pd.DataFrame(columns=["Date"])
        aux_ctx = {"today_row": today, "ALL_DAILY": history}
        aux_ctx.update({k: today.get(v) for k, v in AUX_KEYS.items()})
        for crit in criteria:
            try:
                metrics = crit.compute(df_day, today, aux_ctx, history)
            except Exception as e:  # same as the page: skip this criterion for the day
                name = type(crit).__name__
                errors[name] = errors.get(name, 0) + 1
                log(f"  {d} {name}: {type(e).__name__}: {e}")
                continue
            for m in metrics or ():
                if m.get("dist_col"):
                    today[m["dist_col"]] = m.get("value")
        rows.append(today)
        log(f"  {d}: {len(df_day):>9,} rows, {time.time() - t0:5.1f} s")
        del df_day
    table = pd.DataFrame(rows).sort_values("Date") if rows else pd.DataFrame(columns=["Date"])
    return table, errors


def phases(plan_csv: Path) -> pd.DataFrame:
    """day -> phase and profile, from a scheduler plan (one row per day)."""
    plan = pd.read_csv(plan_csv, usecols=["day", "phase", "profile"])
    plan = plan.drop_duplicates("day")
    plan["Date"] = pd.to_datetime(plan["day"])
    return plan[["Date", "phase", "profile"]]


def run(parquet_dir: Path, datasets: list[str], out_dir: Path, plans_dir: Path | None = None,
        days: list[date] | None = None) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for ds in datasets:
        print(f"{ds}:")
        table, errors = compute_dataset(parquet_dir / ds, days)
        if plans_dir is not None and (plans_dir / f"{ds}.csv").exists() and not table.empty:
            table = table.merge(phases(plans_dir / f"{ds}.csv"), on="Date", how="left")
        table.insert(0, "dataset", ds)
        path = out_dir / f"{ds}.daily.csv"
        table.to_csv(path, index=False)
        written[ds] = path
        print(f"  -> {path} ({len(table)} days)" + (f", criterion errors: {errors}" if errors else ""))
    return written


def parse_day(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def day_range(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]
