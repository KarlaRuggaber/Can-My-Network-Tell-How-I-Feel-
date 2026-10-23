"""Executor tests with a fake clock and fake processes: order, parallel runs, restarts, late blocks, DST."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scheduler import cli, executor

ROOT = Path(__file__).resolve().parent.parent
RUNNER_DEVICES = ROOT.parent / "traffic-runner" / "config" / "devices.csv"
UTC = timezone.utc
T0 = datetime(2026, 10, 26, 7, 0, tzinfo=UTC)


class Clock:
    def __init__(self, t: datetime):
        self.t = t

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


class Proc:
    """Ends `runtime` seconds after launch (on the fake clock) with `code`."""

    def __init__(self, clock, runtime, code=0):
        self.clock, self.until, self.code = clock, clock.now() + timedelta(seconds=runtime), code

    def poll(self):
        return self.code if self.clock.now() >= self.until else None


class Launcher:
    def __init__(self, clock, codes=None):
        self.clock, self.calls, self.codes = clock, [], codes or {}

    def __call__(self, cmd, **kw):
        assert kw["stdin"] is subprocess.DEVNULL and kw["start_new_session"]
        block = cmd[cmd.index("--block-id") + 1]
        duration = int(cmd[cmd.index("--duration") + 1])
        self.calls.append((self.clock.now(), cmd))
        return Proc(self.clock, duration, self.codes.get(block, 0))


def tsv(tmp_path, rows) -> Path:
    """rows: (start, end, device, block_id) with aware datetimes."""
    p = tmp_path / "plan.commands.tsv"
    lines = ["# start\tend\tdevice\tblock_id\tcommand"]
    for s, e, dev, bid in rows:
        dur = int((e - s).total_seconds())
        cmd = (f"scripts/run-activity.sh {dev} --activity phone_check --duration {dur} --mix news:1 "
               f"--seed 1 --profile student --block-id {bid}")
        lines.append("\t".join([s.isoformat(), e.isoformat(), dev, bid, cmd]))
    lines.append("# 2026-10-26T08:00:00+01:00\t...\taway row, ignored")
    p.write_text("\n".join(lines) + "\n")
    return p


def run(tmp_path, rows, start_at, **kw):
    clock = Clock(start_at)
    launch = Launcher(clock, kw.pop("codes", None))
    state = executor.State(tmp_path / "state.jsonl")
    ex = executor.Executor(executor.load_commands(tsv(tmp_path, rows)), state, "/opt/runner", clock=clock,
                           launch=launch, log=lambda m: None, **kw)
    ex.run()
    state.close()
    return launch, clock


def events(tmp_path):
    return [json.loads(x) for x in (tmp_path / "state.jsonl").read_text().splitlines()]


def m(minutes):
    return timedelta(minutes=minutes)


def test_starts_each_block_at_its_time_with_sudo(tmp_path):
    rows = [(T0 + m(10), T0 + m(12), "s_phone", "b1"), (T0 + m(30), T0 + m(31), "s_phone", "b2")]
    launch, _ = run(tmp_path, rows, T0)
    assert [t for t, _ in launch.calls] == [T0 + m(10), T0 + m(30)]
    cmd = launch.calls[0][1]
    assert cmd[:3] == ["sudo", "/opt/runner/scripts/run-activity.sh", "s_phone"]
    assert cmd[cmd.index("--duration") + 1] == "120"
    assert [(e["event"], e["block_id"]) for e in events(tmp_path)] == [
        ("start", "b1"), ("exit", "b1"), ("start", "b2"), ("exit", "b2")]


def test_devices_run_in_parallel(tmp_path):
    rows = [(T0, T0 + m(60), "s_laptop", "stream"), (T0 + m(5), T0 + m(8), "s_phone", "check")]
    launch, _ = run(tmp_path, rows, T0)
    assert [t for t, _ in launch.calls] == [T0, T0 + m(5)]   # the phone does not wait for the laptop


def test_restart_never_starts_a_block_twice(tmp_path):
    rows = [(T0 + m(i), T0 + m(i) + timedelta(seconds=30), "s_phone", f"b{i}") for i in range(4)]
    state = executor.State(tmp_path / "state.jsonl")
    state.record("start", "b0", T0)                   # finished before the reboot
    state.record("exit", "b0", T0 + timedelta(seconds=30), code=0)
    state.record("start", "b1", T0 + m(1))            # killed by the reboot: no exit
    state.close()
    launch, _ = run(tmp_path, rows, T0 + m(1) + timedelta(seconds=40))
    started = [c[c.index("--block-id") + 1] for _, c in launch.calls]
    assert started == ["b2", "b3"]
    assert sum(e["event"] == "start" and e["block_id"] == "b1" for e in events(tmp_path)) == 1


def test_late_blocks_run_shortened_or_are_missed(tmp_path):
    rows = [(T0, T0 + m(60), "s_laptop", "long"),            # 20 min late: 40 min left -> runs 40 min
            (T0 + m(5), T0 + m(8), "s_phone", "short"),       # 15 min late, already over -> missed
            (T0 + m(19) + timedelta(seconds=30), T0 + m(22), "s_phone", "grace")]   # 30 s late -> as planned
    launch, _ = run(tmp_path, rows, T0 + m(20))
    by_block = {c[c.index("--block-id") + 1]: c for _, c in launch.calls}
    assert set(by_block) == {"long", "grace"}
    assert by_block["long"][by_block["long"].index("--duration") + 1] == str(40 * 60)
    assert by_block["grace"][by_block["grace"].index("--duration") + 1] == "150"
    kinds = {e["block_id"]: e["event"] for e in events(tmp_path) if e["event"] != "exit"}
    assert kinds == {"long": "late", "short": "missed", "grace": "start"}


def test_no_catch_up_skips_late_blocks(tmp_path):
    rows = [(T0, T0 + m(60), "s_laptop", "long")]
    launch, _ = run(tmp_path, rows, T0 + m(20), catch_up=False)
    assert not launch.calls
    assert events(tmp_path)[0]["event"] == "missed"


def test_dst_switch_orders_by_absolute_time(tmp_path):
    """25.10.2026: 02:59 CEST is followed by 02:00 CET. Wall-clock order would be wrong."""
    a = datetime.fromisoformat("2026-10-25T02:30:00+02:00")   # 00:30 UTC
    b = datetime.fromisoformat("2026-10-25T02:10:00+01:00")   # 01:10 UTC, earlier wall time, later instant
    rows = [(b, b + m(2), "s_phone", "after_switch"), (a, a + m(2), "s_phone", "before_switch")]
    launch, _ = run(tmp_path, rows, a - m(1))
    assert [c[c.index("--block-id") + 1] for _, c in launch.calls] == ["before_switch", "after_switch"]
    assert launch.calls[1][0] - launch.calls[0][0] == m(40)


def test_exit_codes_are_recorded(tmp_path):
    rows = [(T0, T0 + m(1), "s_phone", "ok"), (T0 + m(2), T0 + m(3), "s_phone", "stub")]
    run(tmp_path, rows, T0, codes={"stub": 3})
    codes = {e["block_id"]: e["code"] for e in events(tmp_path) if e["event"] == "exit"}
    assert codes == {"ok": 0, "stub": 3}


def test_second_executor_on_the_same_plan_is_refused(tmp_path):
    first = executor.State(tmp_path / "state.jsonl")
    with pytest.raises(executor.ExecutorError, match="locked"):
        executor.State(tmp_path / "state.jsonl")
    first.close()
    executor.State(tmp_path / "state.jsonl").close()


def test_launch_failure_is_recorded_and_not_retried(tmp_path):
    def broken(cmd, **kw):
        raise FileNotFoundError("sudo")
    clock = Clock(T0)
    state = executor.State(tmp_path / "state.jsonl")
    ex = executor.Executor(executor.load_commands(tsv(tmp_path, [(T0, T0 + m(1), "s_phone", "b")])), state,
                           "/opt/runner", clock=clock, launch=broken, log=lambda m: None)
    ex.run()
    state.close()
    assert [e["event"] for e in events(tmp_path)] == ["start", "exit"]
    assert executor.State(tmp_path / "state.jsonl").handled("b")


def test_reads_a_real_plan(tmp_path):
    out = tmp_path / "plan.csv"
    assert cli.main(["plan", "--profile", "student", "--seed", "3", "--start", "2026-10-25", "--days", "15",
                     "--devices", str(RUNNER_DEVICES), "--dataset", "gw_student_a", "--out", str(out)]) == 0
    cmds = executor.load_commands(tmp_path / "plan.commands.tsv")
    rows = [x for x in out.read_text().splitlines()[1:] if ",away," not in x]
    assert len(cmds) == len(rows)
    assert cmds == sorted(cmds, key=lambda c: c.start)
    assert cmds[0].start == datetime.fromisoformat(cmds[0].start.isoformat())
    assert all(c.args[0] in ("student_a_phone", "student_a_laptop") for c in cmds)


def test_status_and_dry_run(tmp_path, capsys):
    p = tsv(tmp_path, [(T0, T0 + m(1), "s_phone", "b1"), (T0 + m(600 * 24 * 365), T0 + m(600 * 24 * 365 + 1),
                                                          "s_phone", "b2")])
    state = executor.State(tmp_path / "state.jsonl")
    state.record("start", "b1", T0)
    state.close()
    assert cli.main(["execute", "--commands", str(p), "--state", str(tmp_path / "state.jsonl"), "--status"]) == 0
    out = capsys.readouterr().out
    assert "1 started on time" in out and "1 pending" in out and "next: b2" in out
    assert cli.main(["execute", "--commands", str(p), "--state", str(tmp_path / "s2.jsonl"), "--dry-run"]) == 0
    assert "wait" in capsys.readouterr().out
    assert not (tmp_path / "s2.jsonl").exists()


def test_refuses_a_missing_runner_script(tmp_path):
    p = tsv(tmp_path, [(T0, T0 + m(1), "s_phone", "b1")])
    assert cli.main(["execute", "--commands", str(p), "--state", str(tmp_path / "s.jsonl"),
                     "--runner-dir", str(tmp_path / "nope")]) == 2


def test_executor_needs_no_pyyaml(tmp_path):
    p = tsv(tmp_path, [(T0, T0 + m(1), "s_phone", "b1")])
    code = ("import sys; sys.modules['yaml'] = None; from scheduler import cli; "
            f"sys.exit(cli.main(['execute', '--commands', {str(p)!r}, '--state', {str(tmp_path / 's.jsonl')!r}, "
            "'--status']))")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
