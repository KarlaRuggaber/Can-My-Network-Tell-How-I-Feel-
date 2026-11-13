"""Ground truth of the run: what was scripted when, and what the runner actually executed.

Sources (copied from the gateway into <data_dir>/run/):
- <dataset>.csv          plan: one row per block (start, end, device, activity, phase, profile_block, flag)
- <dataset>.state.jsonl  runner log: "start" (late_s) and "exit" (code) events per block_id
- traffic-runner/config/devices.csv  device -> IP, dataset
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Zurich")  # partitions and metric days are in local time


def load_devices(path: Path) -> dict[str, dict[str, str]]:
    """IP -> {device, role, dataset}."""
    out: dict[str, dict[str, str]] = {}
    try:
        lines = [ln for ln in Path(path).read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError:
        return out
    for row in csv.DictReader(lines):
        if row.get("ip"):
            out[row["ip"].strip()] = {"device": row.get("device", "").strip(),
                                      "role": row.get("role", "").strip(),
                                      "dataset": row.get("dataset", "").strip()}
    return out


def _parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).astimezone(LOCAL_TZ)
    except ValueError:
        return None


def _int(s: Any) -> int | None:
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


@dataclass
class Block:
    block_id: str
    start: datetime
    end: datetime
    device: str
    activity: str
    profile_block: str
    phase: str
    plan_day: str
    mix: str
    flag: str
    profile: str
    companion_of: str
    started_at: datetime | None = None
    late_s: int | None = None
    exited_at: datetime | None = None
    exit_code: int | None = None

    @property
    def status(self) -> str:
        if self.activity == "away":
            return "away"  # device is away from home: nothing is run (commented out in the plan)
        if self.started_at is None:
            return "planned" if self.start > datetime.now(LOCAL_TZ) else "not run"
        if self.exited_at is None:
            return "running"
        return "ok" if self.exit_code == 0 else f"exit {self.exit_code}"

    def to_json(self) -> dict[str, Any]:
        iso = lambda t: t.isoformat() if t else None  # noqa: E731
        return {
            "block_id": self.block_id, "start": iso(self.start), "end": iso(self.end),
            "device": self.device, "activity": self.activity, "profile_block": self.profile_block,
            "phase": self.phase, "plan_day": self.plan_day, "mix": self.mix, "flag": self.flag,
            "profile": self.profile, "companion_of": self.companion_of,
            "started_at": iso(self.started_at), "late_s": self.late_s,
            "exited_at": iso(self.exited_at), "exit_code": self.exit_code, "status": self.status,
        }


def load_plan(run_dir: Path, dataset: str) -> list[Block]:
    path = Path(run_dir) / f"{dataset}.csv"
    if not path.is_file():
        return []
    blocks = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            start, end = _parse_ts(r.get("start")), _parse_ts(r.get("end"))
            if not start or not end or not r.get("block_id"):
                continue
            blocks.append(Block(
                block_id=r["block_id"], start=start, end=end, device=r.get("device", ""),
                activity=r.get("activity_id", ""), profile_block=r.get("profile_block", ""),
                phase=r.get("phase", ""), plan_day=r.get("day", ""), mix=r.get("mix", ""),
                flag=r.get("flag", ""), profile=r.get("profile", ""),
                companion_of=r.get("companion_of", ""),
            ))
    _apply_state(blocks, Path(run_dir) / f"{dataset}.state.jsonl")
    return sorted(blocks, key=lambda b: (b.start, b.device))


def _apply_state(blocks: list[Block], path: Path) -> None:
    if not path.is_file():
        return
    by_id = {b.block_id: b for b in blocks}
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            b = by_id.get(ev.get("block_id", ""))
            if b is None:
                continue
            if ev.get("event") == "start":
                b.started_at, b.late_s = _parse_ts(ev.get("t")), _int(ev.get("late_s"))
            elif ev.get("event") == "exit":
                b.exited_at, b.exit_code = _parse_ts(ev.get("t")), _int(ev.get("code"))


def blocks_on_day(blocks: list[Block], day: date) -> list[Block]:
    """Blocks overlapping the local calendar day [day 00:00, day+1 00:00)."""
    lo = datetime.combine(day, datetime.min.time(), tzinfo=LOCAL_TZ)
    hi = lo + timedelta(days=1)
    return [b for b in blocks if b.start < hi and b.end > lo]


def phase_by_day(blocks: list[Block]) -> dict[str, str]:
    """Plan day -> phase (warmup / baseline / profile), by majority of that day's blocks."""
    counts: dict[str, Counter] = {}
    for b in blocks:
        if b.plan_day:
            counts.setdefault(b.plan_day, Counter())[b.phase] += 1
    return {d: c.most_common(1)[0][0] for d, c in counts.items()}


def day_summary(blocks: list[Block]) -> dict[str, Any]:
    """Compact per-day counts for the timeline: scripted blocks, clinical blocks, sensitive, failures."""
    return {
        "n_blocks": len(blocks),
        "n_profile_blocks": sum(1 for b in blocks if b.phase == "profile"),
        "n_sensitive": sum(1 for b in blocks if b.flag == "sensitive"),
        "n_failed": sum(1 for b in blocks if b.status.startswith("exit")),
        "n_not_run": sum(1 for b in blocks if b.status == "not run"),
        "profile_blocks": dict(Counter(b.profile_block for b in blocks if b.phase == "profile")),
    }
