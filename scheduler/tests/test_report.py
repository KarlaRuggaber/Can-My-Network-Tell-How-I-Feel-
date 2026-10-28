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
    def __init__(self, mem=4000, active=None, kills=(), free=50.0, containers=()):
        # a plain name stands for a host-wide kill
        self._kills = [k if isinstance(k, report.OomKill) else report.OomKill(k, "CONSTRAINT_NONE") for k in kills]
        self._mem, self._active, self._free, self._containers = mem, active or {}, free, set(containers)

    def mem(self):
        return {"MemAvailable": self._mem, "MemTotal": 7100, "SwapTotal": 0, "SwapFree": 0}

    def load(self):
        return 1.5

    def active(self, unit):
        return self._active.get(unit, "active")

    def oom_kills(self, since):
        return self._kills

    def containers(self):
        return self._containers

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


# --- blocks that end before their planned end (25.10: YouTube stream failed after 8 min) --------

def _stream_case(tmp_path, *, logged_end_min=None, running=False):
    """One 2-h video_stream on the laptop, planned 20:15-22:17, report at 22:05 for 21:05-22:05.
    Partitions exist until 20:40. logged_end_min: the runner logged an error that many minutes
    after the start; running: the executor state says the block is running (no log row yet)."""
    start = datetime(2026, 10, 25, 20, 15, tzinfo=Z)
    end = datetime(2026, 10, 25, 22, 17, tzinfo=Z)
    now = datetime(2026, 10, 25, 22, 5, tzinfo=Z).astimezone(UTC)
    row = {c: "" for c in output.PLAN_COLUMNS} | {
        "start": start.isoformat(), "end": end.isoformat(), "device": ROLES["laptop"],
        "activity_id": "video_stream", "block_id": "20261025-weekend_stream-01", "day": "2026-10-25",
        "phase": "warmup", "profile": "9to5-worker", "seed": "1", "dataset": "gw_x_a"}
    plans = tmp_path / "plans"
    plans.mkdir()
    output.write_plan(plans / "gw_x_a.csv", [row])
    gt = []
    if logged_end_min is not None:
        gt.append(row | {"end": (start + timedelta(minutes=logged_end_min)).isoformat(), "status": "error",
                         "domains": "www.youtube.com"})
    write_gt(tmp_path / "gt.csv", gt)
    events = [{"event": "start", "block_id": row["block_id"]}]
    if logged_end_min is not None:
        events.append({"event": "exit", "block_id": row["block_id"], "code": 1})
    (plans / "gw_x_a.state.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    partitions(tmp_path / "pq" / "gw_x_a", datetime(2026, 10, 25, 20, 40, tzinfo=Z).astimezone(UTC),
               back=timedelta(minutes=30))
    return plans, now


def _report(tmp_path, plans, now, hours=1):
    gt = report._ground_truth(tmp_path / "gt.csv")
    return report.dataset_report(plans / "gw_x_a.csv", gt, now, now - timedelta(hours=hours), FakeProbe(),
                                 tmp_path / "pq")


def test_block_that_ended_early_is_not_shown_as_running_and_explains_the_data_gap(tmp_path):
    plans, now = _stream_case(tmp_path, logged_end_min=8)
    d = _report(tmp_path, plans, now)
    assert d.running == []
    assert d.not_running == ["video_stream (x_a_laptop): ended 20:23 (error)"]
    assert not any("capture or ingest" in p for p in d.problems)  # the gap is explained, no false alarm
    assert d.data_note.startswith("no block active since")


def test_early_error_is_reported_in_the_window_where_it_ends_and_only_once(tmp_path):
    plans, now = _stream_case(tmp_path, logged_end_min=8)
    # Hourly watch at :05 with 1-h windows: 20:05-21:05 contains the 20:23 error.
    d = _report(tmp_path, plans, datetime(2026, 10, 25, 21, 5, tzinfo=Z).astimezone(UTC))
    assert len(d.problems) == 1 and "error, ended early at 20:23 (planned until 22:17)" in d.problems[0]
    for hour in (22, 23):  # the later windows, incl. the one after the planned end
        d = _report(tmp_path, plans, datetime(2026, 10, 25, hour, 5, tzinfo=Z).astimezone(UTC))
        assert not any("weekend_stream" in p for p in d.problems), hour  # not pushed again
    daily = _report(tmp_path, plans, datetime(2026, 10, 26, 8, 0, tzinfo=Z).astimezone(UTC), hours=24)
    assert daily.counts["error"] == 1 and len(daily.problems) == 1  # the daily summary lists it once


def test_running_block_without_new_partitions_still_flags_the_data_path(tmp_path):
    plans, now = _stream_case(tmp_path, running=True)
    d = _report(tmp_path, plans, now)
    assert d.running == ["video_stream (x_a_laptop)"]
    assert any("although blocks ran: video_stream (x_a_laptop) (capture or ingest?)" in p for p in d.problems)


# --- OOM kills: host-wide / service containers vs. removed one-off containers (28.10) ---------------

GONE = "78ecaf695c342ce72dd2db1ce7c67819aa622d530fd16a9543483ea564952bff"
RUNNER = "a5e7a901ce04" + "0" * 52
KERNEL = f"""docker-compose invoked oom-killer: gfp_mask=0x140cca(GFP_HIGHUSER_MOVABLE|__GFP_COMP), order=0, oom_score_adj=0
oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=system-traffic\\x2dexecutor.slice,mems_allowed=0,global_oom,task_memcg=/system.slice/docker-07981f5dfd69a3ee307eb9304d2a53cd9a73aae64909edcfd6e3b4dda29ac12a.scope,task=python3,pid=1514703,uid=0
Out of memory: Killed process 1514703 (python3) total-vm:8851796kB, anon-rss:4880276kB, file-rss:600kB, shmem-rss:0kB, UID:0 pgtables:13416kB oom_score_adj:0
oom-kill:constraint=CONSTRAINT_MEMCG,nodemask=(null),cpuset=docker-{GONE}.scope,mems_allowed=0,oom_memcg=/system.slice/docker-{GONE}.scope,task_memcg=/system.slice/docker-{GONE}.scope,task=python3,pid=1543309,uid=0
Memory cgroup out of memory: Killed process 1543309 (python3) total-vm:3557160kB, anon-rss:1531376kB, file-rss:3536kB, shmem-rss:0kB, UID:0 pgtables:3568kB oom_score_adj:0
oom-kill:constraint=CONSTRAINT_MEMCG,nodemask=(null),cpuset=docker-{RUNNER}.scope,mems_allowed=0,oom_memcg=/system.slice/docker-{RUNNER}.scope,task_memcg=/system.slice/docker-{RUNNER}.scope,task=chrome,pid=42,uid=0
Memory cgroup out of memory: Killed process 42 (chrome) total-vm:1kB, anon-rss:1kB, file-rss:0kB, shmem-rss:0kB, UID:0 pgtables:1kB oom_score_adj:0
Killed process 7 (java) total-vm:1kB
"""


def test_parse_oom_reads_constraint_and_cgroup_of_each_kill():
    kills = report.parse_oom(KERNEL)
    assert [(k.name, k.constraint) for k in kills] == [
        ("python3", "CONSTRAINT_NONE"), ("python3", "CONSTRAINT_MEMCG"), ("chrome", "CONSTRAINT_MEMCG"), ("java", "")]
    assert kills[1].cgroup == f"/system.slice/docker-{GONE}.scope"


def test_split_oom_only_removed_capped_containers_are_one_off():
    kills = report.parse_oom(KERNEL)
    problems, oneoff = report.split_oom(kills, {RUNNER})
    assert [k.name for k in oneoff] == ["python3"] and oneoff[0].constraint == "CONSTRAINT_MEMCG"
    # host-wide (27.10 07:31), a runner that still exists, and a kill without details stay problems
    assert [k.name for k in problems] == ["python3", "chrome", "java"]
    # container list unknown: nothing is waved through
    assert len(report.split_oom(kills, None)[0]) == 4


def test_one_off_container_kills_are_listed_but_no_problem(gateway, tmp_path):
    plans, rows, due, now = gateway
    write_gt(tmp_path / "gt.csv", [r | {"status": "ok"} for r in due])
    oneoff = [k for k in report.parse_oom(KERNEL) if GONE in k.cgroup] * 9
    rep = report.build(plans, tmp_path / "gt.csv", tmp_path / "pq", tmp_path / "s.csv", 24,
                       FakeProbe(kills=oneoff, containers={RUNNER}), now)
    assert not any("OOM" in p for p in rep.problems)
    assert "OOM kills: 0; 9 in removed one-off containers at their own memory cap (python3), no problem" in rep.text
