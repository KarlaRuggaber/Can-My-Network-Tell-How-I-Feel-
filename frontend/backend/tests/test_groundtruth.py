from datetime import date

from cmn_frontend import groundtruth as gt
from fixtures import DS, PHONE_IP, make_run


def test_plan_joined_with_runner_state(tmp_path):
    s = make_run(tmp_path)
    blocks = {b.block_id: b for b in gt.load_plan(s.run_dir, DS)}
    assert blocks["b1"].status == "ok" and blocks["b1"].late_s == 3
    assert blocks["b2"].status == "exit 1"
    assert blocks["b3"].status == "not run"      # in the past, never started
    assert blocks["b4"].status == "planned"      # in the future
    blocks["b3"].activity = "away"
    assert blocks["b3"].status == "away"         # away blocks are never run
    assert blocks["b1"].start.utcoffset().total_seconds() == 3600   # local time (CET)


def test_blocks_on_day_uses_overlap_with_local_calendar_day(tmp_path):
    s = make_run(tmp_path)
    blocks = gt.load_plan(s.run_dir, DS)
    on_8 = [b.block_id for b in gt.blocks_on_day(blocks, date(2026, 11, 8))]
    on_9 = [b.block_id for b in gt.blocks_on_day(blocks, date(2026, 11, 9))]
    assert on_8 == ["b1", "b2"]
    assert on_9 == ["b2", "b3"]   # b2 crosses midnight, b3 belongs to plan day 8 but runs on the 9th


def test_phase_and_summary(tmp_path):
    s = make_run(tmp_path)
    blocks = gt.load_plan(s.run_dir, DS)
    assert gt.phase_by_day(blocks)["2026-11-08"] == "baseline"   # 2 baseline vs 1 profile block
    summ = gt.day_summary(gt.blocks_on_day(blocks, date(2026, 11, 9)))
    assert summ["n_blocks"] == 2 and summ["n_sensitive"] == 1 and summ["n_failed"] == 1
    assert summ["profile_blocks"] == {"suicidality": 1}


def test_devices(tmp_path):
    s = make_run(tmp_path)
    devs = gt.load_devices(s.devices_csv)
    assert devs[PHONE_IP] == {"device": "test_a_phone", "role": "phone", "dataset": DS}
    assert gt.load_devices(tmp_path / "missing.csv") == {}
