"""Command line: python -m scheduler {plan,validate}."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import devices as devmod
from . import output, planner, spec

EXIT_OK, EXIT_USAGE = 0, 2


def cmd_plan(args) -> int:
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
    names = args.profiles or sorted(p.stem for p in spec.PROFILE_DIR.glob("*.yaml"))
    for name in names:
        p = spec.load(name)
        print(f"OK: {p.name} (tier {p.tier}, extends {p.extends or '-'}): {len(p.blocks)} blocks, "
              f"{len(p.away)} away periods")
    return EXIT_OK


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
    v = sub.add_parser("validate", help="load and check profile YAMLs")
    v.add_argument("profiles", nargs="*")
    v.set_defaults(func=cmd_validate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (spec.SpecError, devmod.DeviceError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_USAGE
