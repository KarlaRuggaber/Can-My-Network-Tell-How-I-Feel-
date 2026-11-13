"""End to end on synthetic partitions: export with the real metric code, then the API."""

import os
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from cmn_frontend import partitions
from cmn_frontend.api import create_app
from cmn_frontend.export import export_dataset
from cmn_frontend.store import DayStore
from fixtures import DS, make_run


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    s = make_run(tmp_path_factory.mktemp("run"))
    stats = export_dataset(DS, s)
    assert stats == {"computed": 2, "cached": 0}
    return s


def test_partitions_by_day(run):
    by_day = partitions.partitions_by_day(run.processed_dir, DS)
    assert list(by_day) == [date(2026, 11, 8), date(2026, 11, 9)]
    assert len(by_day[date(2026, 11, 8)]) == 3
    assert partitions.list_datasets(run.processed_dir) == [DS]


def test_cache_records(run):
    rec = DayStore(run.cache_dir).load(DS, date(2026, 11, 8))
    assert rec["n_partitions"] == 3 and rec["packets_kept"] > 0
    assert rec["metrics"]["Date"].startswith("2026-11-08")
    assert len(rec["metrics"]) > 20                               # base record + criterion metrics
    act = rec["activity"]
    assert act["bin_minutes"] == 5 and len(act["total"]) == 288
    assert sum(act["total"]) == rec["packets_kept"]
    assert act["total"][8 * 12] > 0 and act["total"][0] == 0      # 08:00 bin has packets, 00:00 none
    assert list(act["devices"]) == ["test_a_phone"]               # other datasets' devices ignored


def test_incremental_and_cascade(run):
    assert export_dataset(DS, run) == {"computed": 0, "cached": 2}
    # rewriting a partition of the first day recomputes it and every later day
    p = sorted((run.processed_dir / DS).glob("*20261108_0800.parquet"))[0]
    t = time.time() + 5
    os.utime(p, (t, t))
    assert export_dataset(DS, run) == {"computed": 2, "cached": 0}
    # a change on the last day only recomputes that day
    p = sorted((run.processed_dir / DS).glob("*20261109_2000.parquet"))[0]
    os.utime(p, (t + 5, t + 5))
    assert export_dataset(DS, run) == {"computed": 1, "cached": 1}


def test_api(run):
    client = TestClient(create_app(run))
    assert client.get("/api/health").json()["datasets"] == [DS]

    cfg = client.get("/api/config").json()
    assert cfg["theta"] == pytest.approx(0.6) and cfg["core"] == ["C2"]
    assert cfg["metric_labels"]["C4_F2_WakeAfter0400Min"]
    assert cfg["metric_criterion"]["C4_F2_WakeAfter0400Min"] == "C4"

    personas = client.get("/api/personas").json()
    assert personas[0]["dataset"] == DS and personas[0]["n_days"] == 2

    tl = client.get(f"/api/personas/{DS}").json()
    d0, d1 = tl["days"]
    assert (d0["date"], d0["phase"], d0["complete"]) == ("2026-11-08", "baseline", True)
    assert d1["complete"] is False                              # newest day: still being ingested
    assert d1["ground_truth"]["n_sensitive"] == 1
    assert d0["L"]["C3"] is None                                # not configured
    assert 0.0 <= d0["L"]["C1"] <= 1.0
    assert set(d0["parts"]["C4"]) == set(cfg["criteria"]["C4"])
    assert set(tl["gate"]["present"]) == {c for c, s in cfg["criteria"].items() if s}
    assert len(tl["gate"]["episode"]) == 2

    day = client.get(f"/api/personas/{DS}/days/2026-11-09").json()
    assert [b["block_id"] for b in day["blocks"]] == ["b2", "b3"]
    assert len(day["activity"]["total"]) == 288

    assert client.get("/api/personas/nope").status_code == 404
    assert client.get(f"/api/personas/{DS}/days/2026-01-01").status_code == 404
    assert client.get(f"/api/personas/{DS}/days/xx").status_code == 400


def test_ip_cache_does_not_change_results(run):
    from cmn_frontend import daily
    from cmn_frontend.store import history_frame
    files = partitions.partitions_by_day(run.processed_dir, DS)[date(2026, 11, 8)]
    try:
        plain = daily.compute_day(files, date(2026, 11, 8), history_frame([]),
                                  daily.load_metric_code(run.app_dir, ip_cache=False), {})
        cached = daily.compute_day(files, date(2026, 11, 8), history_frame([]),
                                   daily.load_metric_code(run.app_dir, ip_cache=True), {})
    finally:
        daily.load_metric_code(run.app_dir)
    assert plain["metrics"] == cached["metrics"]
