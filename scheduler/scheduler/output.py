"""Write a Plan as the ground-truth plan CSV and as runner commands (scheduler/README.md §5)."""

from __future__ import annotations

import csv
import shlex
from pathlib import Path
from zoneinfo import ZoneInfo

from . import catalog
from .planner import Entry, Plan

# The runner's ground-truth columns first (catalog §1, without `status`), then what the runner needs and
# what traces a row back to the profile.
PLAN_COLUMNS = ["start", "end", "device", "activity_id", "domains", "profile", "seed", "block_id",
                "mix", "duration", "pages", "dwell", "lookups", "platform", "options", "day", "phase", "dataset",
                "profile_block", "companion_of", "flag"]
COMMAND_COLUMNS = ["start", "end", "device", "block_id", "command"]
RUN_SCRIPT = "scripts/run-activity.sh"   # relative to traffic-runner/


def _iso(dt, tz) -> str:
    return dt.astimezone(tz).isoformat(timespec="seconds")


def _fmt_weight(w: float) -> str:
    return f"{w:g}"


def runner_mix(e: Entry) -> str:
    if not e.mix or any(k in catalog.NO_RUNNER_MIX for k in e.mix):
        return ""
    return ",".join(f"{k}:{_fmt_weight(w)}" for k, w in e.mix.items())


def rows(plan: Plan, devices: dict[str, str], dataset: str) -> list[dict[str, str]]:
    tz = ZoneInfo(plan.profile.timezone)
    out = []
    for e in plan.entries:
        out.append({
            "start": _iso(e.start, tz), "end": _iso(e.end, tz), "device": devices[e.role],
            "activity_id": e.activity, "domains": ";".join(e.mix) if e.mix else "",
            "profile": e.profile, "seed": str(plan.seed), "block_id": e.block_id,
            "mix": runner_mix(e), "duration": str(int((e.end - e.start).total_seconds())),
            "pages": e.pages or "", "dwell": e.dwell or "", "lookups": e.lookups or "",
            "platform": e.platform or "", "options": e.options or "",
            "day": e.day.isoformat(), "phase": e.phase, "dataset": dataset, "profile_block": e.profile_block,
            "companion_of": e.companion_of or "", "flag": e.flag or "",
        })
    return out


def command(row: dict[str, str]) -> str:
    args = [RUN_SCRIPT, row["device"], "--activity", row["activity_id"], "--duration", row["duration"]]
    if row["mix"]:
        args += ["--mix", row["mix"]]
    args += ["--seed", row["seed"], "--profile", row["profile"], "--block-id", row["block_id"]]
    if row["pages"]:
        args += ["--pages", row["pages"]]
    if row["dwell"]:
        args += ["--dwell", row["dwell"]]
    if row["lookups"]:
        args += ["--lookups", row["lookups"]]
    return shlex.join(args)


def write_plan(path: Path, plan_rows: list[dict[str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PLAN_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(plan_rows)


def write_commands(path: Path, plan_rows: list[dict[str, str]]) -> None:
    """Tab-separated, one runner call per row, sorted by start. `away` has no runner implementation (a
    container cannot leave the Wi-Fi), so those rows are written as comments for the executor."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# " + "\t".join(COMMAND_COLUMNS) + "\n")
        f.write("# run from traffic-runner/ on the gateway; start each command at `start` (absolute, Europe/Zurich)\n")
        for r in plan_rows:
            line = "\t".join([r["start"], r["end"], r["device"], r["block_id"], command(r)])
            f.write(("# " + line if r["activity_id"] == "away" else line) + "\n")
