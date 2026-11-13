"""Compare the app's daily metrics of one day between a live and a synthetic dataset.

Headless version of the app's per-day pipeline (pages/02_Network_Metrics.py,
compute_or_load_all_days_features): load the day's 5-min partitions, enrich_with_hostnames,
drop_background, compute_daily_base_record, then Criterion1..9.compute. No Streamlit, so it
runs on a laptop with little memory (the app itself needs several GB).

Both datasets get the same empty history (ALL_DAILY), so only same-day values are compared;
metrics that need earlier days (14/30-day z-scores, variances) come out as NaN on both sides.

    python3 synthesizer/compare_day.py --day 2026-10-28 \
        --pair ~/cmnthif-synth/processed_parquet/gw_mdd_suicidality_a ~/cmnthif-synth/processed_parquet/syn_mdd_suicidality_b \
        [--pair LIVE SYN ...] [--csv out.csv]

Needs pandas, numpy and pyarrow (e.g. the ingest venv app_pcap_to_dsm5/.venv).
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

import pandas as pd

APP = Path(__file__).resolve().parent.parent / "app_pcap_to_dsm5" / "app"
sys.path.insert(0, str(APP))

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

PART_RE = re.compile(r"__(\d{8})_(\d{4})\.parquet$")
CRITERIA = (Criterion1, Criterion2, Criterion3, Criterion4, Criterion5, Criterion6, Criterion7, Criterion8, Criterion9)


def load_day(dataset_dir: Path, day: pd.Timestamp) -> pd.DataFrame:
    """The day's partitions, as the app's load_day_dataframe reads them."""
    key = day.strftime("%Y%m%d")
    files = sorted(p for p in dataset_dir.glob("*.parquet") if (m := PART_RE.search(p.name)) and m.group(1) == key)
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")
    df = df[(df["Timestamp"] >= day) & (df["Timestamp"] < day + pd.Timedelta(days=1))].copy()
    df["Date"] = df["Timestamp"].dt.date
    df["Hour"] = df["Timestamp"].dt.hour
    return df


def day_metrics(dataset_dir: Path, day: pd.Timestamp) -> tuple[dict, dict, int, int]:
    """(metric values by dist_col, labels by dist_col, raw rows, rows after the background filter)."""
    raw = load_day(dataset_dir, day)
    if raw.empty:
        return {}, {}, 0, 0
    df = drop_background(enrich_with_hostnames(raw))
    rec = compute_daily_base_record(df)
    values, labels = {}, {}
    history = pd.DataFrame()
    for cls in CRITERIA:
        for m in cls().compute(df, dict(rec), dict(today_row=rec, ALL_DAILY=history), history):
            col = m.get("dist_col") or m.get("label")
            values[col] = m.get("value")
            labels[col] = f"{cls.__name__.replace('Criterion', 'C')}: {m.get('label')}"
    return values, labels, len(raw), len(df)


def as_float(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return math.nan
    return f if math.isfinite(f) else math.nan


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--day", required=True, help="YYYY-MM-DD (local Europe/Zurich day, as the app)")
    p.add_argument("--pair", nargs=2, action="append", required=True, metavar=("LIVE", "SYN"),
                   help="live and synthetic dataset folders (processed_parquet/<name>)")
    p.add_argument("--csv", help="write all rows to this CSV")
    args = p.parse_args(argv)
    day = pd.Timestamp(args.day)
    rows = []
    for live_dir, syn_dir in args.pair:
        live_dir, syn_dir = Path(live_dir).expanduser(), Path(syn_dir).expanduser()
        lv, labels, l_raw, l_kept = day_metrics(live_dir, day)
        sv, s_labels, s_raw, s_kept = day_metrics(syn_dir, day)
        labels = {**s_labels, **labels}
        print(f"\n== {live_dir.name} vs {syn_dir.name}, {args.day}: rows live {l_raw:,} ({l_kept:,} after background filter), "
              f"synthetic {s_raw:,} ({s_kept:,})")
        for col in sorted(set(lv) | set(sv), key=lambda c: labels.get(c, c)):
            a, b = as_float(lv.get(col)), as_float(sv.get(col))
            diff = b - a if not (math.isnan(a) or math.isnan(b)) else math.nan
            rel = diff / abs(a) if not math.isnan(diff) and a != 0 else math.nan
            rows.append({"live": live_dir.name, "synthetic": syn_dir.name, "metric": col,
                         "label": labels.get(col, col), "live_value": a, "syn_value": b, "diff": diff, "rel_diff": rel})
    out = pd.DataFrame(rows)
    if args.csv:
        out.to_csv(Path(args.csv).expanduser(), index=False)
    with pd.option_context("display.width", 220, "display.max_rows", None, "display.max_colwidth", 70):
        for (lname, sname), g in out.groupby(["live", "synthetic"], sort=False):
            print(f"\n{lname} vs {sname}")
            print(g[["label", "live_value", "syn_value", "diff", "rel_diff"]].to_string(index=False, float_format=lambda x: f"{x:.3g}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
