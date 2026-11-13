"""Compute (or update) the per-day cache for one or more datasets.

    python -m cmn_frontend.export                       # all datasets in processed_parquet
    python -m cmn_frontend.export gw_insomnia_a         # one dataset
    python -m cmn_frontend.export --watch 900           # repeat every 15 min (live run)

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
    code = code or daily.load_metric_code(settings.app_dir)
    store = DayStore(settings.cache_dir)
    version = code_version(settings.app_dir)
    devices = {ip: d["device"] for ip, d in load_devices(settings.devices_csv).items()
               if d.get("dataset") == dataset}
    by_day = partitions_by_day(settings.processed_dir, dataset)
    all_days = sorted(by_day)
    stats = {"computed": 0, "cached": 0}
    history: list[dict] = []
    dirty = force
    for day in all_days:
        if until and day > until:
            break
        files = by_day[day]
        sig = day_signature(files)
        cached = store.load(dataset, day)
        if (not dirty and cached and cached.get("signature") == sig
                and cached.get("code_version") == version):
            stats["cached"] += 1
            history.append(cached)
            continue
        dirty = True  # every later day sees a changed history
        t0 = time.monotonic()
        rec = daily.compute_day(files, day, history_frame(history), code, devices)
        last_start = max((partition_start(p) for p in files), default=None)
        rec.update({
            "dataset": dataset,
            "date": day.isoformat(),
            "signature": sig,
            "code_version": version,
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "n_partitions": len(files),
            "last_partition_start": last_start.isoformat() if last_start else None,
            "seconds": round(time.monotonic() - t0, 1),
        })
        store.save(dataset, day, rec)
        history.append(rec)
        stats["computed"] += 1
        log.info("%s %s: %d partitions, %d packets kept, %.0f s",
                 dataset, day, len(files), rec["packets_kept"], rec["seconds"])
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
                    log.info("%s: %d day(s) computed, %d unchanged", ds, stats["computed"], stats["cached"])
        else:
            for ds in datasets:
                stats = export_dataset(ds, settings, code, force=args.force, until=args.until)
                log.info("%s: %d day(s) computed, %d unchanged", ds, stats["computed"], stats["cached"])
        if not args.watch:
            return 0
        args.force = False
        time.sleep(args.watch)


if __name__ == "__main__":
    sys.exit(main())
