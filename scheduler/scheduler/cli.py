"""Command line: python -m scheduler {plan,validate,execute,report}.

`execute` and `report` run on the gateway and need only the standard library; the planning modules (PyYAML)
are imported inside `plan` and `validate`.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

EXIT_OK, EXIT_USAGE = 0, 2


def _seconds(text: str) -> float:
    from .dist import parse_duration
    return parse_duration(text).bounds()[0]


def cmd_plan(args) -> int:
    from . import devices as devmod
    from . import output, planner, spec
    profile = spec.load(args.profile)
    baseline = None
    if args.baseline_days:
        if profile.tier == 0 or profile.root == profile.name:
            raise ValueError(f"{profile.name} is a tier-0 profile; --baseline-days is for clinical profiles")
        baseline = spec.load(profile.root)
    rows_ = devmod.load(args.devices)
    roles = devmod.map_roles(rows_, args.dataset, profile.devices)

    plan = planner.build_plan(profile, args.seed, args.start, args.days, baseline=baseline,
                              baseline_days=args.baseline_days, any_start=args.any_start)
    for w in plan.warnings:
        print(f"warning: {w}", file=sys.stderr)
    plan_rows = output.rows(plan, roles, args.dataset)
    out = Path(args.out)
    output.write_plan(out, plan_rows)
    commands = Path(args.commands) if args.commands else out.with_suffix(".commands.tsv")
    output.write_commands(commands, plan_rows)

    first, last = plan.phases[0].dates[0], plan.phases[-1].dates[-1]
    phases = ", ".join(f"{p.name} {len(p.dates)} d ({p.profile.name})" for p in plan.phases)
    print(f"{out}: {len(plan_rows)} rows, {first} .. {last}: {phases}", file=sys.stderr)
    print(f"{commands}: runner commands", file=sys.stderr)
    if plan.dropped:
        print("dropped occurrences: " + ", ".join(f"{k} {v}" for k, v in sorted(plan.dropped.items())),
              file=sys.stderr)
    return EXIT_OK


def cmd_validate(args) -> int:
    from . import spec
    names = args.profiles or sorted(p.stem for p in spec.PROFILE_DIR.glob("*.yaml"))
    for name in names:
        p = spec.load(name)
        print(f"OK: {p.name} (tier {p.tier}, extends {p.extends or '-'}): {len(p.blocks)} blocks, "
              f"{len(p.away)} away periods")
    return EXIT_OK


def cmd_execute(args) -> int:
    from . import executor
    return executor.main(args)


def cmd_report(args) -> int:
    from . import report
    return report.main(args)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m scheduler", description="Profile + seed -> ground-truth plan")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("plan", help="write the plan CSV and the runner commands")
    r.add_argument("--profile", required=True, help="name in scheduler/profiles/ (e.g. student) or a .yaml path")
    r.add_argument("--seed", required=True, type=int, help="profile instance seed")
    r.add_argument("--start", required=True, type=date.fromisoformat, help="first plan day = warm-up day, YYYY-MM-DD (a Sunday: the window starts on Monday)")
    r.add_argument("--days", type=int, default=15, help="total days in the plan, incl. warm-up (default 15)")
    r.add_argument("--baseline-days", type=int, default=0,
                   help="clinical profiles: days after the warm-up that run the tier-0 baseline (e.g. 14)")
    r.add_argument("--any-start", action="store_true",
                   help="allow a --start that does not put the window on the profile's start weekday (pilots, tests)")
    r.add_argument("--devices", required=True, help="traffic-runner/config/devices.csv")
    r.add_argument("--dataset", required=True, help="dataset in devices.csv, e.g. gw_student_a")
    r.add_argument("--out", required=True, help="plan CSV")
    r.add_argument("--commands", help="runner commands TSV (default: <out>.commands.tsv)")
    r.set_defaults(func=cmd_plan)
    e = sub.add_parser("execute", help="replay a plan's runner commands live (gateway; stdlib only)")
    e.add_argument("--commands", required=True, help="plan.commands.tsv written by `plan`")
    e.add_argument("--state", required=True,
                   help="state file of started blocks (JSON lines), e.g. /var/lib/traffic-executor/gw_student_a.jsonl")
    e.add_argument("--runner-dir", default="/opt/can-my-network/traffic-runner",
                   help="traffic-runner clone with scripts/run-activity.sh (default: the gateway clone)")
    e.add_argument("--no-sudo", action="store_true", help="call run-activity.sh without sudo")
    e.add_argument("--grace", type=_seconds, default=60.0, help="start late by up to this as planned (default 60s)")
    e.add_argument("--min-remaining", type=_seconds, default=300.0,
                   help="a later block runs with the time left if at least this is left (default 5m)")
    e.add_argument("--no-catch-up", action="store_true", help="skip every block later than --grace")
    e.add_argument("--log-dir", help="one log file per block (runner output); default: the executor's stdout")
    e.add_argument("--status", action="store_true", help="print progress from the state file and exit")
    e.add_argument("--dry-run", action="store_true", help="print what would happen now, write nothing")
    e.add_argument("--dry-run-rows", type=int, default=20)
    e.set_defaults(func=cmd_execute)
    g = sub.add_parser("report", help="push report: plan vs. ground truth, executors, data, gateway (stdlib only)")
    g.add_argument("--plans", default="/var/lib/traffic-executor",
                   help="folder with gw_*.csv plans and their .state.jsonl files (default: the executor folder)")
    g.add_argument("--ground-truth", default="/opt/can-my-network/traffic-runner/logs/ground_truth.csv")
    g.add_argument("--parquet", default="/opt/can-my-network/app_pcap_to_dsm5/app/processed_parquet")
    g.add_argument("--samples", default="/var/lib/traffic-executor/gateway-samples.csv",
                   help="memory samples written by --sample")
    g.add_argument("--hours", type=float, default=24.0, help="window to check (default 24)")
    g.add_argument("--only-problems", action="store_true", help="send only if there is a problem (hourly watch)")
    g.add_argument("--ntfy", help="ntfy topic URL, e.g. https://ntfy.sh/<random topic> (default: $NTFY_URL)")
    g.add_argument("--ntfy-token", help="ntfy access token (default: $NTFY_TOKEN)")
    g.add_argument("--sample", action="store_true", help="append one memory sample and exit (every minute)")
    g.set_defaults(func=cmd_report)
    v = sub.add_parser("validate", help="load and check profile YAMLs")
    v.add_argument("profiles", nargs="*")
    v.set_defaults(func=cmd_validate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, RuntimeError) as e:   # SpecError, DeviceError, ExecutorError are subclasses
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
