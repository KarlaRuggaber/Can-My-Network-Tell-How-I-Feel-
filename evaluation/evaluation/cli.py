"""Command line: python -m evaluation {daily,compare}."""

from __future__ import annotations

import argparse
from pathlib import Path

DATASETS = ["gw_insomnia_a", "gw_mdd_suicidality_a", "gw_social_anxiety_a"]


def cmd_daily(args) -> int:
    from . import daily
    if args.peer_external:
        daily.peer_external()
    days = None
    if args.day:
        days = [daily.parse_day(d) for d in args.day]
    elif args.first or args.last:
        days = daily.day_range(daily.parse_day(args.first or "2026-10-25"), daily.parse_day(args.last or "2026-11-22"))
    daily.run(Path(args.parquet).expanduser(), args.dataset or DATASETS, Path(args.out).expanduser(),
              Path(args.plans).expanduser() if args.plans else None, days)
    return 0


def cmd_compare(args) -> int:
    from . import compare
    from .daily import APP_DIR
    cfg = Path(args.config).expanduser() if args.config else APP_DIR / "fasl_config.json"
    out = compare.report(Path(args.eval).expanduser(), cfg, Path(args.out).expanduser(), args.all_metrics)
    print(out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m evaluation", description="Evaluate the live run against the profiles")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("daily", help="daily metrics per dataset, as the app's Early Signs page computes them")
    d.add_argument("--parquet", default="~/cmn-data/processed_parquet", help="processed_parquet folder")
    d.add_argument("--dataset", action="append", help=f"dataset (repeatable; default: {', '.join(DATASETS)})")
    d.add_argument("--plans", default="~/cmn-data/run", help="folder with the scheduler plans <dataset>.csv (phases)")
    d.add_argument("--out", default="~/cmn-data/eval", help="output folder for <dataset>.daily.csv")
    d.add_argument("--day", action="append", help="only this day (YYYY-MM-DD), repeatable")
    d.add_argument("--first", help="first day")
    d.add_argument("--last", help="last day")
    d.add_argument("--peer-external", action="store_true",
                   help="variant: count the peer stack (10.43.0.0/24) as internet, so calls and games are up/download")
    d.set_defaults(func=cmd_daily)
    c = sub.add_parser("compare", help="baseline vs. clinical phase per persona, against expectations.yaml")
    c.add_argument("--eval", default="~/cmn-data/eval", help="folder with <dataset>.daily.csv")
    c.add_argument("--config", help="fasl config (default: the app's fasl_config.json, the original thesis config)")
    c.add_argument("--out", default="~/cmn-data/eval/report.md")
    c.add_argument("--all-metrics", action="store_true", help="also list every metric that changed")
    c.set_defaults(func=cmd_compare)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
