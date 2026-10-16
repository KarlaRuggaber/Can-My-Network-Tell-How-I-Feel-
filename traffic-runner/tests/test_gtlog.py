"""Ground-truth log format and concurrent appends."""

import csv
import multiprocessing as mp
import re

import pytest

from runner import gtlog

ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")


def row(i=0, status="ok"):
    return {"start": gtlog.now_iso(), "end": gtlog.now_iso(), "device": f"dev{i}", "activity_id": "browse",
            "domains": "www.nzz.ch;www.20min.ch", "profile": "student", "seed": 42, "block_id": f"b{i:03}",
            "status": status}


def test_header_once_and_format(tmp_path):
    p = tmp_path / "gt.csv"
    gtlog.append(row(1), p)
    gtlog.append(row(2, "not_implemented"), p)
    lines = p.read_text().splitlines()
    assert lines[0] == "start,end,device,activity_id,domains,profile,seed,block_id,status"
    rows = list(csv.DictReader(p.open()))
    assert [r["status"] for r in rows] == ["ok", "not_implemented"]
    assert ISO.match(rows[0]["start"]) and ISO.match(rows[0]["end"])
    assert rows[0]["domains"] == "www.nzz.ch;www.20min.ch"


def test_zurich_offset(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Zurich")
    assert gtlog.now_iso()[-6:] in ("+01:00", "+02:00")


def test_rejects_bad_rows(tmp_path):
    with pytest.raises(ValueError):
        gtlog.append(row(1, "maybe"), tmp_path / "gt.csv")
    bad = row(1)
    del bad["status"]
    with pytest.raises(ValueError):
        gtlog.append(bad, tmp_path / "gt.csv")


def test_refuses_foreign_header(tmp_path):
    p = tmp_path / "gt.csv"
    p.write_text("a,b,c\n")
    with pytest.raises(RuntimeError):
        gtlog.append(row(1), p)


def _writer(args):
    path, worker = args
    for i in range(50):
        gtlog.append(row(worker * 1000 + i), path)


def test_concurrent_writers(tmp_path):
    p = tmp_path / "gt.csv"
    with mp.get_context("spawn").Pool(4) as pool:
        pool.map(_writer, [(p, w) for w in range(4)])
    lines = p.read_text().splitlines()
    assert lines.count(lines[0]) == 1  # header written exactly once
    rows = list(csv.DictReader(p.open()))
    assert len(rows) == 200
    assert all(len(r) == 9 and r["status"] == "ok" for r in rows)
