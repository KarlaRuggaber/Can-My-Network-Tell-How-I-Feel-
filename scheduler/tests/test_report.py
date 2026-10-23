"""Push report tests: a fake gateway folder (plan, ground-truth log, state, partitions) and a fake system probe."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from scheduler import cli, output, planner, report, spec

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc
Z = report.ZURICH
GT_FIELDS = ["start", "end", "device", "activity_id", "domains", "profile", "seed", "block_id", "status"]
ROLES = {"phone": "x_a_phone", "laptop": "x_a_laptop"}


class FakeProbe(report.Probe):
    def __init__(self, mem=4000, active=None, kills=(), free=50.0):
        self._mem, self._active, self._kills, self._free = mem, active or {}, list(kills), free

    def mem(self):
        return {"MemAvailable": self._mem, "MemTotal": 7100, "SwapTotal": 0, "SwapFree": 0}

    def load(self):
        return 1.5

    def active(self, unit):
        return self._active.get(unit, "active")

    def oom_kills(self, since):
        return self._kills

    def free_gb(self, path):
        return self._free


@pytest.fixture
def gateway(tmp_path):
    """A student plan from Sun 25.10; `now` = Tue 27.10 08:00, so the window is Mon 26.10 08:00 - Tue 08:00."""
    plan = planner.build_plan(spec.load("student"), 4, date(2026, 10, 25), 15)
    rows = output.rows(plan, ROLES, "gw_x_a")
    plans = tmp_path / "plans"
    plans.mkdir()
    output.write_plan(plans / "gw_x_a.csv", rows)
    now = datetime(2026, 10, 27, 8, 0, tzinfo=Z).astimezone(UTC)
    since = now - timedelta(hours=24)
    due = [r for r in rows if r["activity_id"] != "away" and report._t(r["start"]) >= since
           and report._t(r["end"]) <= now - report.SETTLE]
    assert len(due) > 20
    return plans, rows, due, now


def write_gt(path, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=GT_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in GT_FIELDS if k != "status"} | {"status": r["status"]})


def partitions(folder, now, every=timedelta(minutes=5), back=timedelta(hours=24)):
    folder.mkdir(parents=True)
    t = now - back
    while t <= now:
        loc = t.astimezone(Z)
        (folder / f"gw_x_a__{loc:%Y%m%d_%H}{loc.minute - loc.minute % 5:02d}.parquet").touch()
        t += every


def test_all_good(gateway, tmp_path):
    plans, rows, due, now = gateway
    gt = [r | {"status": "not_implemented" if r["activity_id"] in report.RUNNER_STUBS else "ok"} for r in due]
    write_gt(tmp_path / "gt.csv", gt)
    partitions(tmp_path / "pq" / "gw_x_a", now)
    rep = report.build(plans, tmp_path / "gt.csv", tmp_path / "pq", tmp_path / "samples.csv", 24, FakeProbe(), now)
    assert rep.problems == [], rep.problems
    assert rep.title.startswith("Gateway: all good")
    assert "day 3/15, profile (student)" in rep.text
    stubs = sum(r["activity_id"] in report.RUNNER_STUBS for r in due)
    assert f"{len(due)} blocks due: {len(due) - stubs} ok, {stubs} stub, 0 problem(s)" in rep.text


def test_problems_are_named(gateway, tmp_path):
    plans, rows, due, now = gateway
    by_act = {}
    for r in due:
        by_act.setdefault(r["activity_id"], []).append(r)
    phone_checks = [r for r in due if r["activity_id"] == "phone_check"]
    bad = {
        phone_checks[0]["block_id"]: "error",
        phone_checks[1]["block_id"]: "missed",
        phone_checks[2]["block_id"]: "interrupted",
        phone_checks[3]["block_id"]: "not started",
        phone_checks[4]["block_id"]: "logged twice",
    }
    gt, state = [], []
    for r in due:
        what = bad.get(r["block_id"])
        if what is None:
            gt.append(r | {"status": "not_implemented" if r["activity_id"] in report.RUNNER_STUBS else "ok"})
        elif what == "error":
            gt.append(r | {"status": "error"})
        elif what == "logged twice":
            gt += [r | {"status": "ok"}, r | {"status": "ok"}]
        elif what == "missed":
            state.append({"event": "missed", "block_id": r["block_id"]})
        elif what == "interrupted":
            state.append({"event": "start", "block_id": r["block_id"]})
    late = phone_checks[5]
    gt = [g if g["block_id"] != late["block_id"] else
          g | {"start": (report._t(g["start"]) + timedelta(minutes=10)).astimezone(Z).isoformat()} for g in gt]
    write_gt(tmp_path / "gt.csv", gt)
    (plans / "gw_x_a.state.jsonl").write_text("".join(json.dumps(e) + "\n" for e in state) + '{"broken')
    rep = report.build(plans, tmp_path / "gt.csv", tmp_path / "pq", tmp_path / "s.csv", 24,
                       FakeProbe(mem=200, active={"traffic-executor@gw_x_a": "failed", "tapingest": "inactive"},
                                 kills=["chrome", "java"], free=3.0), now)
    text = "\n".join(rep.problems)
    for bid, what in bad.items():
        assert f"{bid} phone_check" in text and what in text, (bid, what)
    assert "executor traffic-executor@gw_x_a is failed" in text
    assert "no new Parquet partition since never" in text
    assert "memory went down to 200 MB" in text
    assert "OOM killer ended chrome, java" in text
    assert "only 3.0 GB free" in text
    assert "tapingest is inactive" in text
    assert "1 late" in rep.text
    assert rep.title.startswith(f"Gateway: {len(rep.problems)} problem(s)")


def test_unexpected_not_implemented_is_a_problem(gateway, tmp_path):
    """Calls log not_implemented when the peer stack is down: that is a problem, a messaging stub is not."""
    plans, rows, due, now = gateway
    gt = [r | {"status": "not_implemented"} for r in due]
    write_gt(tmp_path / "gt.csv", gt)
    partitions(tmp_path / "pq" / "gw_x_a", now)
    rep = report.build(plans, tmp_path / "gt.csv", tmp_path / "pq", tmp_path / "s.csv", 24, FakeProbe(), now)
    flagged = {p.split()[1] for p in rep.problems}
    assert flagged == {r["block_id"] for r in due if r["activity_id"] not in report.RUNNER_STUBS}


def test_memory_minimum_comes_from_the_samples(gateway, tmp_path):
    plans, rows, due, now = gateway
    samples = tmp_path / "s.csv"
    for i, mb in enumerate([3000, 250, 2800]):
        report.sample(samples, FakeProbe(mem=mb), now - timedelta(hours=3 - i))
    report.sample(samples, FakeProbe(mem=100), now - timedelta(hours=30))   # outside the window
    assert report._sample_min(samples, now - timedelta(hours=24)) == 250
    write_gt(tmp_path / "gt.csv", [])
    rep = report.build(plans, tmp_path / "gt.csv", tmp_path / "pq", samples, 24, FakeProbe(mem=3500), now)
    assert "min 250 MB in window" in rep.text
    assert any("memory went down to 250 MB" in p for p in rep.problems)


def test_ntfy_push(monkeypatch, gateway, tmp_path):
    plans, rows, due, now = gateway
    sent = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b""

    def fake_urlopen(req, timeout):
        sent.append(req)
        return Resp()
    monkeypatch.setattr(report.urllib.request, "urlopen", fake_urlopen)
    rep = report.Report("Gateway: 1 problem(s)", "body", ["x"])
    report.send_ntfy("https://ntfy.sh/topic-abc", rep, token="tok")
    req = sent[0]
    assert req.full_url == "https://ntfy.sh/topic-abc" and req.data == b"body"
    assert req.get_header("Title") == "Gateway: 1 problem(s)" and req.get_header("Priority") == "high"
    assert req.get_header("Authorization") == "Bearer tok"


def test_only_problems_sends_nothing_when_all_is_well(monkeypatch, gateway, tmp_path):
    plans, rows, due, now = gateway
    monkeypatch.setattr(report, "build", lambda *a, **k: report.Report("Gateway: all good", "fine", []))
    monkeypatch.setattr(report, "Probe", FakeProbe)
    called = []
    monkeypatch.setattr(report, "send_ntfy", lambda *a, **k: called.append(a))
    base = ["report", "--plans", str(plans), "--ground-truth", str(tmp_path / "gt.csv"), "--ntfy", "https://x/t"]
    assert cli.main(base + ["--only-problems"]) == 0 and not called
    assert cli.main(base) == 0 and len(called) == 1


def test_report_needs_no_pyyaml(tmp_path):
    code = ("import sys; sys.modules['yaml'] = None; from scheduler import cli, report; "
            "sys.exit(cli.main(['report', '--help']))")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
