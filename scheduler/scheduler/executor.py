"""Executor: replays a plan's runner commands live on the gateway (scheduler/README.md §5.1).

Reads `plan.commands.tsv`, waits for each block's absolute start time and launches
`sudo <runner-dir>/scripts/run-activity.sh <device> ...` as its own process (blocks on several devices run in
parallel). Away rows are comments in the file: away simply means no run.

Never twice: every block ID is written to a state file (JSON lines, fsync) *before* its process starts. After
a restart or a reboot, every block that has a state entry is skipped, also one whose process was killed by the
reboot (its ground-truth row is then missing, which the plan/log join shows).

Late blocks (executor down, gateway rebooting): within `grace` of the start the block runs as planned. Later,
it runs with the remaining time (`--duration` = end - now) if at least `min_remaining` is left, else it is
recorded as missed.

Stdlib only (no PyYAML), so it runs with the gateway's system python3.
"""

from __future__ import annotations

import fcntl
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")
RUN_SCRIPT = "scripts/run-activity.sh"   # as written by output.py, relative to the runner directory
MAX_SLEEP = 30.0                          # seconds; short enough to reap finished runs and follow clock changes
UTC = timezone.utc


class ExecutorError(RuntimeError):
    pass


@dataclass(frozen=True)
class Command:
    start: datetime
    end: datetime
    device: str
    block_id: str
    args: list[str]          # everything after scripts/run-activity.sh


def load_commands(path: str | Path) -> list[Command]:
    out, seen = [], set()
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, start=1):
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.split("\t")
            if len(fields) != 5:
                raise ExecutorError(f"{path}:{n}: expected 5 tab-separated fields, got {len(fields)}")
            start, end = (datetime.fromisoformat(x) for x in fields[:2])
            if start.tzinfo is None or end.tzinfo is None:
                raise ExecutorError(f"{path}:{n}: times need a UTC offset")
            args = shlex.split(fields[4])
            if not args or args[0] != RUN_SCRIPT or "--duration" not in args:
                raise ExecutorError(f"{path}:{n}: not a {RUN_SCRIPT} call with --duration")
            if fields[3] in seen:
                raise ExecutorError(f"{path}:{n}: block {fields[3]} appears twice")
            seen.add(fields[3])
            out.append(Command(start.astimezone(UTC), end.astimezone(UTC), fields[2], fields[3], args[1:]))
    out.sort(key=lambda c: (c.start, c.device, c.block_id))   # absolute times: DST days sort correctly
    return out


def with_duration(args: list[str], seconds: int) -> list[str]:
    args = list(args)
    args[args.index("--duration") + 1] = str(seconds)
    return args


class State:
    """Append-only JSON lines: one entry per event (start, late, missed, exit). Locked against a second
    executor on the same plan; `readonly` (for --status) reads without the lock, while an executor runs."""

    def __init__(self, path: str | Path, readonly: bool = False):
        self.path = Path(path)
        self.readonly = readonly
        self.events: dict[str, list[dict]] = {}
        if readonly:
            self._f = None
            lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._f = open(self.path, "a+", encoding="utf-8")
            try:
                fcntl.flock(self._f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self._f.close()
                raise ExecutorError(f"{self.path} is locked: another executor runs this plan") from None
            self._f.seek(0)
            lines = self._f.read().splitlines()
        for line in lines:
            if line.strip():
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    if readonly:   # a line the running executor is writing right now
                        continue
                    raise
                self.events.setdefault(e["block_id"], []).append(e)

    def handled(self, block_id: str) -> bool:
        return any(e["event"] in ("start", "late", "missed") for e in self.events.get(block_id, ()))

    def record(self, event: str, block_id: str, at: datetime, **fields) -> None:
        if self._f is None:
            raise ExecutorError("state opened read-only")
        e = {"t": at.isoformat(timespec="seconds"), "event": event, "block_id": block_id, **fields}
        self._f.write(json.dumps(e) + "\n")
        self._f.flush()
        os.fsync(self._f.fileno())
        self.events.setdefault(block_id, []).append(e)

    def unfinished(self) -> list[str]:
        """Blocks started earlier without a recorded exit (still running, or killed by a reboot)."""
        return [b for b, es in self.events.items()
                if any(e["event"] in ("start", "late") for e in es) and not any(e["event"] == "exit" for e in es)]

    def close(self) -> None:
        if self._f is not None:
            self._f.close()


class RealClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class Executor:
    def __init__(self, commands: list[Command], state: State, runner_dir: str | Path, *, sudo: bool = True,
                 grace: float = 60, min_remaining: float = 300, catch_up: bool = True,
                 log_dir: str | Path | None = None, clock=None, launch=subprocess.Popen, log=None):
        self.commands, self.state = commands, state
        self.script = Path(runner_dir) / RUN_SCRIPT
        self.sudo, self.grace, self.min_remaining, self.catch_up = sudo, grace, min_remaining, catch_up
        self.log_dir = Path(log_dir) if log_dir else None
        self.clock = clock or RealClock()
        self.launch = launch
        self.log = log or (lambda msg: print(msg, flush=True))
        self.running: dict[str, tuple[object, Command, object]] = {}

    def decide(self, c: Command, now: datetime) -> tuple[str, int]:
        """('start' | 'late' | 'missed', duration in seconds) for a block whose start time has come."""
        planned = int((c.end - c.start).total_seconds())
        late = (now - c.start).total_seconds()
        if late <= self.grace:
            return "start", planned
        remaining = int((c.end - now).total_seconds())
        if self.catch_up and remaining >= self.min_remaining:
            return "late", remaining
        return "missed", 0

    def run(self) -> int:
        """Run every pending block; returns when all are started and all processes have ended."""
        pending = [c for c in self.commands if not self.state.handled(c.block_id)]
        unfinished = self.state.unfinished()
        if unfinished:
            self.log(f"{len(unfinished)} block(s) were started before without a recorded exit "
                     f"(interrupted or still running), not started again: {', '.join(unfinished[:5])}"
                     + (" ..." if len(unfinished) > 5 else ""))
        self.log(f"{len(pending)} of {len(self.commands)} block(s) pending")
        for c in pending:
            while True:
                now = self.clock.now()
                if now >= c.start:
                    break
                self._reap()
                self.clock.sleep(min((c.start - now).total_seconds(), MAX_SLEEP))
            self._reap()
            self._start(c, self.clock.now())
        while self.running:
            self._reap()
            if self.running:
                self.clock.sleep(5)
        self.log("plan done")
        return 0

    def _start(self, c: Command, now: datetime) -> None:
        what, duration = self.decide(c, now)
        late = int((now - c.start).total_seconds())
        if what == "missed":
            self.state.record("missed", c.block_id, now, device=c.device, late_s=late)
            self.log(f"missed {c.block_id} on {c.device} ({late} s late, too little time left)")
            return
        args = c.args if what == "start" else with_duration(c.args, duration)
        cmd = (["sudo"] if self.sudo else []) + [str(self.script), *args]
        self.state.record(what, c.block_id, now, device=c.device, late_s=late, duration=duration)   # before launching
        out = None
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            out = open(self.log_dir / f"{c.block_id}.log", "a", encoding="utf-8")
        try:
            # own session: stopping/restarting the executor doesn't stop running blocks (systemd: KillMode=process)
            p = self.launch(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT if out else None,
                            start_new_session=True)
        except OSError as e:
            self.state.record("exit", c.block_id, self.clock.now(), code=None, error=str(e))
            self.log(f"could not start {c.block_id}: {e}")
            if out:
                out.close()
            return
        self.running[c.block_id] = (p, c, out)
        self.log(f"{what} {c.block_id} on {c.device}, {duration} s" + (f" ({late} s late)" if what == "late" else ""))

    def _reap(self) -> None:
        for bid, (p, c, out) in list(self.running.items()):
            code = p.poll()
            if code is None:
                continue
            self.state.record("exit", bid, self.clock.now(), code=code)
            if code not in (0, 3):   # runner: 0 ok, 1 error, 2 usage, 3 not_implemented
                self.log(f"{bid} on {c.device} exited with {code}")
            if out:
                out.close()
            del self.running[bid]


def status(commands: list[Command], state: State, now: datetime) -> str:
    counts = {"pending": 0, "start": 0, "late": 0, "missed": 0}
    codes: dict[str, int] = {}
    for c in commands:
        es = state.events.get(c.block_id, [])
        kind = next((e["event"] for e in es if e["event"] in ("start", "late", "missed")), "pending")
        counts[kind] += 1
        for e in es:
            if e["event"] == "exit":
                codes[str(e.get("code"))] = codes.get(str(e.get("code")), 0) + 1
    nxt = next((c for c in commands if not state.handled(c.block_id) and c.start >= now), None)
    lines = [f"{len(commands)} blocks: {counts['start']} started on time, {counts['late']} late, "
             f"{counts['missed']} missed, {counts['pending']} pending",
             "exit codes: " + (", ".join(f"{k}: {v}" for k, v in sorted(codes.items())) or "-"),
             f"running or interrupted: {len(state.unfinished())}"]
    if nxt:
        lines.append(f"next: {nxt.block_id} on {nxt.device} at {nxt.start.astimezone(ZURICH).isoformat(timespec='seconds')}")
    return "\n".join(lines)


def main(args) -> int:
    """Entry point for `python -m scheduler execute` (arguments parsed in cli.py)."""
    commands = load_commands(args.commands)
    if args.dry_run:
        ex = Executor(commands, None, args.runner_dir, grace=args.grace, min_remaining=args.min_remaining,
                      catch_up=not args.no_catch_up)
        now = datetime.now(UTC)
        for c in commands[: args.dry_run_rows]:
            what = "wait" if c.start > now else ex.decide(c, now)[0]
            print(f"{c.start.astimezone(ZURICH).isoformat(timespec='seconds')}  {what:6s}  {c.device}  {c.block_id}")
        return 0
    if args.status:   # read-only: works while the executor runs
        print(status(commands, State(args.state, readonly=True), datetime.now(UTC)))
        return 0
    state = State(args.state)
    try:
        script = Path(args.runner_dir) / RUN_SCRIPT
        if not os.access(script, os.X_OK):
            raise ExecutorError(f"{script} is missing or not executable (--runner-dir)")
        ex = Executor(commands, state, args.runner_dir, sudo=not args.no_sudo, grace=args.grace,
                      min_remaining=args.min_remaining, catch_up=not args.no_catch_up, log_dir=args.log_dir)

        def stop(signum, frame):
            raise SystemExit(128 + signum)
        signal.signal(signal.SIGTERM, stop)   # running blocks keep going (own session), state stays consistent
        return ex.run()
    finally:
        state.close()
        sys.stdout.flush()
