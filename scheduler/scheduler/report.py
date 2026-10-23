"""Push report for the live runs (scheduler/README.md §5.2): plan vs. ground-truth log, executors, data, gateway.

    python3 -m scheduler report --hours 24 --ntfy https://ntfy.sh/<topic>        # daily summary
    python3 -m scheduler report --hours 1 --only-problems --ntfy ...             # hourly watch: only if something is wrong
    python3 -m scheduler report --sample                                          # every minute: memory sample

Per dataset (a `gw_*.csv` plan in --plans) it checks every block that should have finished in the window:
a ground-truth row with status ok, or a stub (RUNNER_STUBS), or else a problem: error, not_implemented,
missed / interrupted / not started (from the executor's state file), logged twice. It also reports whether the
executor runs and whether new Parquet partitions arrive, plus memory (minimum from the samples), OOM kills,
disk and the capture/ingest services. Stdlib only, like the executor.
"""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .catalog import RUNNER_STUBS

ZURICH = ZoneInfo("Europe/Zurich")
UTC = timezone.utc
LATE = timedelta(minutes=2)          # a block counts as late if its ground-truth start is later than this
SETTLE = timedelta(minutes=3)        # a block is checked once it should have ended this long ago
STALE = timedelta(minutes=30)        # no new partition for this long while blocks ran = data path problem
LOW_MEMORY_MB = 300
LOW_DISK_GB = 5
SERVICES = ["tapcap@eno1", "tapcap@br-sim", "tapingest", "docker"]
_PARTITION_RE = re.compile(r"__(\d{8})_(\d{4})\.parquet$")


def _t(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def _local(dt: datetime, fmt: str = "%a %d.%m %H:%M") -> str:
    return dt.astimezone(ZURICH).strftime(fmt)


# --- system probes (replaced in tests) ----------------------------------------------------------------

class Probe:
    def mem(self) -> dict[str, int]:
        """MemAvailable, SwapTotal, SwapFree in MB."""
        out = {}
        if not os.path.exists("/proc/meminfo"):   # not Linux (development machine)
            return out
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, rest = line.partition(":")
                if key in ("MemAvailable", "MemTotal", "SwapTotal", "SwapFree"):
                    out[key] = int(rest.split()[0]) // 1024
        return out

    def load(self) -> float:
        return os.getloadavg()[0]

    def active(self, unit: str) -> str:
        r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
        return r.stdout.strip() or "unknown"

    def oom_kills(self, since: datetime) -> list[str] | None:
        """Names of processes the kernel's OOM killer ended since `since` (None: journal not readable)."""
        try:
            r = subprocess.run(["journalctl", "-k", "--no-pager", "-o", "cat", "--since",
                                since.astimezone().strftime("%Y-%m-%d %H:%M:%S")], capture_output=True, text=True)
        except FileNotFoundError:
            return None
        if r.returncode != 0:
            return None
        return re.findall(r"Killed process \d+ \(([^)]+)\)", r.stdout)

    def free_gb(self, path: str | Path) -> float | None:
        try:
            return shutil.disk_usage(path).free / 1e9
        except OSError:
            return None


# --- data --------------------------------------------------------------------------------------------

@dataclass
class DatasetReport:
    dataset: str
    checked: int = 0
    counts: Counter = field(default_factory=Counter)      # ok, stub, error, missing, ...
    late: int = 0
    problems: list[str] = field(default_factory=list)
    running: list[str] = field(default_factory=list)
    phase: str = ""
    day: str = ""
    executor: str = ""
    newest_partition: datetime | None = None
    partitions_in_window: int = 0
    next_block: str = ""


def _ground_truth(path: Path) -> dict[tuple[str, str], list[dict]]:
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    if path.exists():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                out[(row["device"], row["block_id"])].append(row)
    return out


def _state(path: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    if path.exists():   # read without the executor's lock (advisory, append-only file)
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue   # a line being written right now
                out[e["block_id"]].append(e)
    return out


def _classify(row: dict, gt: dict, state: dict) -> tuple[str, bool]:
    """(outcome, late) of one planned block that should have finished."""
    logged = gt.get((row["device"], row["block_id"]), [])
    if len(logged) > 1:
        return "logged twice", False
    if logged:
        g = logged[0]
        late = _t(g["start"]) - _t(row["start"]) > LATE
        if g["status"] == "ok":
            return "ok", late
        if g["status"] == "not_implemented" and row["activity_id"] in RUNNER_STUBS:
            return "stub", late
        return g["status"], late
    events = state.get(row["block_id"], [])
    kinds = [e["event"] for e in events]
    if "missed" in kinds:
        return "missed", False
    if any(k in ("start", "late") for k in kinds):
        exits = [e for e in events if e["event"] == "exit"]
        return ("interrupted" if not exits else f"no log row (exit {exits[-1].get('code')})"), False
    return "not started", False


GOOD = {"ok", "stub"}


def dataset_report(plan_path: Path, gt: dict, now: datetime, since: datetime, probe: Probe,
                   parquet_dir: Path) -> DatasetReport:
    ds = plan_path.stem
    rep = DatasetReport(ds)
    with open(plan_path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["activity_id"] != "away"]
    state = _state(plan_path.with_name(f"{ds}.state.jsonl"))
    days = sorted({r["day"] for r in rows})
    today = now.astimezone(ZURICH).date().isoformat()
    todays = [r for r in rows if r["day"] == today]
    if todays:
        rep.phase = f"{todays[0]['phase']} ({todays[0]['profile']})"
        rep.day = f"day {days.index(today) + 1}/{len(days)}"
    elif days and today > days[-1]:
        rep.phase, rep.day = "done", f"ended {days[-1]}"
    elif days:
        rep.phase, rep.day = "not started", f"starts {days[0]}"

    for r in rows:
        start, end = _t(r["start"]), _t(r["end"])
        if start <= now < end:
            rep.running.append(f"{r['activity_id']} ({r['device']})")
        if not (since <= start and end <= now - SETTLE):
            continue
        rep.checked += 1
        outcome, late = _classify(r, gt, state)
        rep.counts[outcome] += 1
        rep.late += late
        if outcome not in GOOD:
            rep.problems.append(f"{ds}: {r['block_id']} {r['activity_id']} on {r['device']} at "
                                f"{_local(start, '%d.%m %H:%M')}: {outcome}")
    upcoming = [r for r in rows if _t(r["start"]) > now]
    if upcoming:
        n = min(upcoming, key=lambda r: _t(r["start"]))
        rep.next_block = f"{n['activity_id']} {_local(_t(n['start']))}"

    rep.executor = probe.active(f"traffic-executor@{ds}")
    if upcoming and rep.executor != "active":
        rep.problems.append(f"{ds}: executor traffic-executor@{ds} is {rep.executor}, {len(upcoming)} blocks still to come")

    folder = parquet_dir / ds
    if folder.is_dir():
        for p in folder.iterdir():
            m = _PARTITION_RE.search(p.name)
            if not m:
                continue
            t = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M").replace(tzinfo=ZURICH).astimezone(UTC)
            rep.newest_partition = max(rep.newest_partition or t, t)
            rep.partitions_in_window += since <= t <= now
    ran_recently = [r for r in rows if _t(r["start"]) < now - STALE and _t(r["end"]) > since]
    if ran_recently and (rep.newest_partition is None or rep.newest_partition < now - STALE - timedelta(minutes=5)):
        last = _local(rep.newest_partition) if rep.newest_partition else "never"
        rep.problems.append(f"{ds}: no new Parquet partition since {last} although blocks ran (capture or ingest?)")
    return rep


@dataclass
class Report:
    title: str
    text: str
    problems: list[str]


def build(plans_dir: Path, gt_path: Path, parquet_dir: Path, samples: Path, hours: float, probe: Probe,
          now: datetime | None = None) -> Report:
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=hours)
    gt = _ground_truth(gt_path)
    datasets = [dataset_report(p, gt, now, since, probe, parquet_dir) for p in sorted(plans_dir.glob("gw_*.csv"))]
    problems = [p for d in datasets for p in d.problems]

    lines = [f"Window {_local(since)} - {_local(now)} ({hours:g} h)"]
    if not datasets:
        problems.append(f"no plan (gw_*.csv) in {plans_dir}")
    for d in datasets:
        c = d.counts
        bad = sum(v for k, v in c.items() if k not in GOOD)
        lines.append(f"{d.dataset}: {d.day}, {d.phase}; executor {d.executor}")
        lines.append(f"  {d.checked} blocks due: {c['ok']} ok, {c['stub']} stub, {bad} problem(s), {d.late} late")
        data = (f"newest partition {_local(d.newest_partition)}, {d.partitions_in_window} in window"
                if d.newest_partition else "no partitions yet")
        lines.append(f"  data: {data}")
        if d.running:
            lines.append(f"  running now: {', '.join(d.running)}")
        if d.next_block:
            lines.append(f"  next: {d.next_block}")

    mem = probe.mem()
    sampled = _sample_min(samples, since)
    swap_used = mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)
    gw = (f"Gateway: {mem.get('MemAvailable', 0)} MB available now"
          + (f", min {sampled} MB in window" if sampled is not None else ", no memory samples")
          + f", swap used {swap_used} MB, load {probe.load():.1f}")
    lines.append(gw)
    low = sampled if sampled is not None else mem.get("MemAvailable", 0)
    if low < LOW_MEMORY_MB:
        problems.append(f"gateway: memory went down to {low} MB available")
    kills = probe.oom_kills(since)
    if kills is None:
        lines.append("OOM kills: journal not readable")
    else:
        lines.append(f"OOM kills: {len(kills)}" + (f" ({', '.join(sorted(set(kills)))})" if kills else ""))
        if kills:
            problems.append(f"gateway: OOM killer ended {', '.join(sorted(set(kills)))}")
    for path in (parquet_dir, Path("/var/lib/tapcap")):
        gb = probe.free_gb(path)
        if gb is not None:
            lines.append(f"Disk free at {path}: {gb:.1f} GB")
            if gb < LOW_DISK_GB:
                problems.append(f"gateway: only {gb:.1f} GB free at {path}")
    states = {s: probe.active(s) for s in SERVICES}
    lines.append("Services: " + ", ".join(f"{s} {v}" for s, v in states.items()))
    problems += [f"gateway: {s} is {v}" for s, v in states.items() if v != "active"]

    if problems:
        lines.append("")
        lines.append(f"Problems ({len(problems)}):")
        lines += [f"- {p}" for p in problems[:25]]
        if len(problems) > 25:
            lines.append(f"- ... and {len(problems) - 25} more")
    title = (f"Gateway: {len(problems)} problem(s)" if problems else "Gateway: all good") + f" ({_local(now, '%d.%m %H:%M')})"
    return Report(title, "\n".join(lines), problems)


# --- memory samples ----------------------------------------------------------------------------------

def sample(path: Path, probe: Probe, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    mem = probe.mem()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{now.isoformat(timespec='seconds')},{mem.get('MemAvailable', 0)},"
                f"{mem.get('SwapTotal', 0) - mem.get('SwapFree', 0)},{probe.load():.2f}\n")


def _sample_min(path: Path, since: datetime) -> int | None:
    if not path.exists():
        return None
    low = None
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split(",")
        if len(parts) < 2:
            continue
        try:
            t, avail = _t(parts[0]), int(parts[1])
        except ValueError:
            continue
        if t >= since:
            low = avail if low is None else min(low, avail)
    return low


# --- sending -----------------------------------------------------------------------------------------

def send_ntfy(url: str, rep: Report, token: str | None = None) -> None:
    """ntfy (https://ntfy.sh or self-hosted): an HTTP POST to a topic URL; the phone app shows it as a push."""
    headers = {"Title": rep.title, "Priority": "high" if rep.problems else "default",
               "Tags": "warning" if rep.problems else "white_check_mark"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=rep.text.encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def main(args) -> int:
    probe = Probe()
    if args.sample:
        sample(Path(args.samples), probe)
        return 0
    rep = build(Path(args.plans), Path(args.ground_truth), Path(args.parquet), Path(args.samples), args.hours, probe)
    print(rep.title)
    print(rep.text)
    if args.only_problems and not rep.problems:
        return 0
    url = args.ntfy or os.environ.get("NTFY_URL")
    if url:
        send_ntfy(url, rep, args.ntfy_token or os.environ.get("NTFY_TOKEN"))
    return 0
