"""Compute (or update) the per-day cache for one or more datasets.

    python -m cmn_frontend.export                       # all datasets in processed_parquet
    python -m cmn_frontend.export gw_insomnia_a         # one dataset
    python -m cmn_frontend.export --watch 900           # repeat every 15 min (live run)

Metric rows are taken from the evaluation's daily tables (~/cmn-data/eval/<dataset>.daily.csv)
where they exist; only days missing there are computed here, with the same thesis code.

Runs on the laptop. Memory: about one day of packets per job (~1-2 GB); --jobs N processes
N datasets in parallel (days within a dataset stay sequential: some metrics read the history).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timezone

from . import daily
from .groundtruth import load_devices
from .partitions import day_signature, list_datasets, partition_start, partitions_by_day
from .settings import Settings, load_settings
from .store import DayStore, code_version, history_frame

log = logging.getLogger("cmn_frontend.export")


def export_dataset(dataset: str, settings: Settings, code: daily.MetricCode | None = None,
                   force: bool = False, until: date | None = None) -> dict[str, int]:
    """Update the per-day cache of one dataset.

    Metric rows come from the evaluation's daily table (<daily_tables>/<dataset>.daily.csv) when it
    has the day and is newer than the day's partitions; only the traffic summary is computed then.
    Other days (e.g. the current one) are computed with the thesis metric code, using the
    previous rows as history. Days before the table's first day (pre-run captures) are skipped,
    so the history matches the evaluation's.
    """
    code = code or daily.load_metric_code(settings.app_dir)
    store = DayStore(settings.cache_dir)
    version = code_version(settings.app_dir)
    devices = {ip: d["device"] for ip, d in load_devices(settings.devices_csv).items()
               if d.get("dataset") == dataset}
    table_path = settings.daily_tables / f"{dataset}.daily.csv"
    table = daily.load_daily_table(table_path)
    table_mtime = table_path.stat().st_mtime if table else 0.0
    table_sig = f"{table_mtime:.0f}" if table else ""
    first_table_day = min(table) if table else None

    by_day = partitions_by_day(settings.processed_dir, dataset)
    stats = {"computed": 0, "imported": 0, "cached": 0, "skipped": 0}
    history: list[dict] = []
    dirty = force
    for day in sorted(by_day):
        if until and day > until:
            break
        if first_table_day and day < first_table_day:
            store.remove(dataset, day)
            stats["skipped"] += 1
            continue
        files = by_day[day]
        sig = day_signature(files)
        newest = max((p.stat().st_mtime for p in files), default=0.0)
        use_table = day in table and table_mtime >= newest
        source = "table" if use_table else "computed"
        cached = store.load(dataset, day)
        if (not dirty and cached and cached.get("signature") == sig
                and cached.get("code_version") == version and cached.get("source") == source
                and (source == "computed" or cached.get("table_signature") == table_sig)):
            stats["cached"] += 1
            history.append(cached)
            continue
        t0 = time.monotonic()
        if use_table:
            rec = daily.activity_for_day(files, day, code, devices)
            rec["metrics"] = table[day]
            stats["imported"] += 1
        else:
            dirty = True  # later computed days see a changed history
            rec = daily.compute_day(files, day, history_frame(history), code, devices)
            stats["computed"] += 1
        last_start = max((partition_start(p) for p in files), default=None)
        rec.update({
            "dataset": dataset,
            "date": day.isoformat(),
            "source": source,
            "table_signature": table_sig if use_table else None,
            "signature": sig,
            "code_version": version,
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_partitions": len(files),
            "last_partition_start": last_start.isoformat() if last_start else None,
            "seconds": round(time.monotonic() - t0, 1),
        })
        store.save(dataset, day, rec)
        history.append(rec)
        log.info("%s %s: %s, %d partitions, %d packets kept, %.0f s", dataset, day,
                 "metrics from daily table" if use_table else "metrics computed",
                 len(files), rec["packets_kept"], rec["seconds"])
    return stats


def _init_worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")


def _export_one(dataset: str, force: bool, until: date | None) -> dict[str, int]:
    return export_dataset(dataset, load_settings(), force=force, until=until)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m cmn_frontend.export", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datasets", nargs="*", help="dataset names (default: all in processed_parquet)")
    ap.add_argument("--force", action="store_true", help="recompute every day")
    ap.add_argument("--until", type=date.fromisoformat, help="stop after this day (YYYY-MM-DD)")
    ap.add_argument("--watch", type=int, metavar="SECONDS", help="repeat every SECONDS")
    ap.add_argument("--jobs", type=int, default=1, help="datasets processed in parallel (default 1)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    settings = load_settings()
    code = daily.load_metric_code(settings.app_dir)
    while True:
        datasets = args.datasets or list_datasets(settings.processed_dir)
        if not datasets:
            log.error("no datasets in %s", settings.processed_dir)
            return 1
        if args.jobs > 1 and len(datasets) > 1:
            with ProcessPoolExecutor(max_workers=min(args.jobs, len(datasets)),
                                     initializer=_init_worker) as pool:
                results = pool.map(_export_one, datasets, [args.force] * len(datasets),
                                   [args.until] * len(datasets))
                for ds, stats in zip(datasets, results):
                    log.info("%s: %s", ds, stats)
        else:
            for ds in datasets:
                stats = export_dataset(ds, settings, code, force=args.force, until=args.until)
                log.info("%s: %s", ds, stats)
        if not args.watch:
            return 0
        args.force = False
        time.sleep(args.watch)


if __name__ == "__main__":
    sys.exit(main())
