"""Command line: python -m synthesizer {cut,coverage,build,trace}.

`build` and `cut` need only the standard library (`cut` uses PyYAML if --mixes is given); `trace` needs pandas +
pyarrow, like the app.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

EXIT_OK, EXIT_ERROR, EXIT_USAGE = 0, 1, 2
REPO = Path(__file__).resolve().parents[2]
DEFAULT_DEVICES = REPO / "traffic-runner" / "config" / "devices.csv"
DEFAULT_MIXES = REPO / "traffic-runner" / "config" / "mixes.yaml"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def cmd_cut(args) -> int:
    from . import library
    devices = library.apply_aliases(library.load_devices(args.devices), args.alias)
    info = library.load_block_info(args.plan, args.commands)
    mixes = None if args.no_mixes else args.mixes
    library.cut(args.ground_truth, args.captures, devices, args.library, info, mixes, args.tail,
                tuple(args.status), log=_log)
    return EXIT_OK


def cmd_coverage(args) -> int:
    from .build import coverage
    rows = coverage(args.plan, args.library, args.devices, args.day, args.strict)
    cols = ["activity_id", "rows", "planned_h", "exact", "fallback", "none", "copies", "snippets"]
    print("\t".join(cols))
    for r in rows:
        print("\t".join(str(r[c]) for c in cols))
    return EXIT_OK


def cmd_build(args) -> int:
    from .build import build
    build(args.plan, args.library, args.devices, args.dataset, args.out, args.day, args.seed, args.strict,
          args.target_devices, log=_log)
    return EXIT_OK


def cmd_trace(args) -> int:
    from .trace import trace
    rows, stats = trace(args.out, args.parquet)
    cols = ["block_id", "activity_id", "manifest_packets", "parquet_rows", "missing"]
    print("\t".join(cols))
    for r in rows:
        print("\t".join(str(r[c]) for c in cols))
    _log(f"{stats['rows']} Parquet rows, {stats['untraced']} without a segment, "
         f"{stats['dst_ambiguous']} in the repeated DST hour (not traced)")
    return EXIT_OK if stats["untraced"] == 0 else EXIT_ERROR


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m synthesizer", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cut", help="cut recorded blocks into the snippet library")
    c.add_argument("--ground-truth", required=True, help="traffic-runner/logs/ground_truth.csv")
    c.add_argument("--captures", action="append", required=True, help="tapcap folder (sim/ready), repeatable")
    c.add_argument("--library", required=True, help="library folder (created; new snippets are added)")
    c.add_argument("--devices", default=DEFAULT_DEVICES, help="devices.csv (default: %(default)s)")
    c.add_argument("--alias", action="append", default=[], metavar="OLD=NEW",
                   help="device renamed since the recording, e.g. student01_phone=student_a_phone")
    c.add_argument("--plan", action="append", default=[], help="plan.csv of the recorded run (mix, options)")
    c.add_argument("--commands", action="append", default=[], help="plan.commands.tsv of the recorded run")
    c.add_argument("--mixes", default=DEFAULT_MIXES, help="runner mixes.yaml for host -> category (default: %(default)s)")
    c.add_argument("--no-mixes", action="store_true", help="built-in host table only (no PyYAML needed)")
    c.add_argument("--tail", type=float, default=30, help="seconds after a block's end kept as its tail (default: 30)")
    c.add_argument("--status", action="append", default=None, help="ground-truth status to cut (default: ok)")
    c.set_defaults(func=cmd_cut)

    for name, helptext in (("build", "synthesize a plan (or some of its days)"),
                           ("coverage", "how a plan would be built from the library, per activity")):
        b = sub.add_parser(name, help=helptext)
        b.add_argument("--plan", required=True, help="plan.csv from python -m scheduler plan")
        b.add_argument("--library", required=True)
        b.add_argument("--devices", default=DEFAULT_DEVICES, help="devices.csv (default: %(default)s)")
        b.add_argument("--day", action="append", default=None, help="only plan rows of this day (YYYY-MM-DD), repeatable")
        b.add_argument("--strict", action="store_true", help="no role/mix/option fallbacks: such rows stay empty")
        if name == "build":
            b.add_argument("--dataset", required=True, help="synthetic dataset name, e.g. syn_insomnia_b")
            b.add_argument("--out", required=True, help="output folder for this instance (ready/ must be empty)")
            b.add_argument("--seed", default=None, help="selection seed (default: the plan's seed)")
            b.add_argument("--target-devices", default=None,
                           help="devices file with the target IP/MAC per plan device (default: --devices)")
            b.set_defaults(func=cmd_build)
        else:
            b.set_defaults(func=cmd_coverage)

    t = sub.add_parser("trace", help="Parquet rows of an ingested instance -> packets per block_id")
    t.add_argument("--out", required=True, help="the build's output folder (segments.csv, manifest.csv)")
    t.add_argument("--parquet", required=True, help="processed_parquet/<dataset>")
    t.set_defaults(func=cmd_trace)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if getattr(args, "status", None) is None and args.cmd == "cut":
        args.status = ["ok"]
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as e:
        _log(f"error: {e}")
        return EXIT_USAGE
