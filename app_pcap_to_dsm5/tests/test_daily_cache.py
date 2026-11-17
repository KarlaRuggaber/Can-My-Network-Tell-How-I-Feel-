"""metrics.daily_cache: per-day records in a child process, incremental cache file.

Run from app_pcap_to_dsm5/:  python -m pytest tests
"""

import math
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from metrics import daily_cache as dc  # noqa: E402

DS = "gw_test_a"
CLIENT, GW = "10.42.1.31", "10.42.1.1"
SITES = [("www.reddit.com", "151.101.1.140"), ("www.youtube.com", "142.250.1.1"), ("www.srf.ch", "23.1.2.3")]


def _rows(day: str, hour: int, n_flows: int) -> list[dict]:
    """A DNS lookup + a short TCP flow per site, every few minutes in one hour."""
    rows = []
    for k in range(n_flows):
        host, ip = SITES[k % len(SITES)]
        t = pd.Timestamp(f"{day} {hour:02d}:00:00") + pd.Timedelta(minutes=2 * k)
        base = dict(Protocol="UDP", **{"TCP Flags": None}, IsDNS=True, DNS_QTYPE=1.0, **{"Capture File": "cap-1.pcap"})
        rows.append({**base, "Timestamp": t, "Source IP": CLIENT, "Destination IP": GW, "Source Port": 50000 + k,
                     "Destination Port": 53, "Length": 80, "DNS_QNAME": host, "DNS_ANS_IPS": None, "DNS_ANS_NAME": None})
        rows.append({**base, "Timestamp": t + pd.Timedelta(milliseconds=5), "Source IP": GW, "Destination IP": CLIENT,
                     "Source Port": 53, "Destination Port": 50000 + k, "Length": 120, "DNS_QNAME": None,
                     "DNS_ANS_IPS": ip, "DNS_ANS_NAME": host})
        for j in range(20):
            out = j % 2 == 0
            rows.append({"Timestamp": t + pd.Timedelta(seconds=1 + j), "Protocol": "TCP", "TCP Flags": "PA",
                         "IsDNS": False, "DNS_QTYPE": float("nan"), "Capture File": "cap-1.pcap",
                         "Source IP": CLIENT if out else ip, "Destination IP": ip if out else CLIENT,
                         "Source Port": 40000 + k if out else 443, "Destination Port": 443 if out else 40000 + k,
                         "Length": 200 if out else 1400, "DNS_QNAME": None, "DNS_ANS_IPS": None, "DNS_ANS_NAME": None})
    return rows


def _write_partition(root: Path, day: str, hour: int, n_flows: int) -> Path:
    df = pd.DataFrame(_rows(day, hour, n_flows))
    df["Date"] = df["Timestamp"].dt.date.astype(str)
    df["Hour"] = df["Timestamp"].dt.hour
    d = root / DS
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{DS}__{day.replace('-', '')}_{hour:02d}00.parquet"
    df.to_parquet(path, index=False)
    return path


@pytest.fixture
def data(tmp_path):
    proc = tmp_path / "processed_parquet"
    for day in ("2026-10-27", "2026-10-28"):
        for hour, n in ((8, 6), (13, 9), (21, 4)):
            _write_partition(proc, day, hour, n)
    return proc, tmp_path / "feature_cache"


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    try:
        if pd.isna(a) and pd.isna(b):
            return True
    except (TypeError, ValueError):
        pass
    return a == b


def test_child_process_gives_the_same_record(data):
    proc, _ = data
    inproc = dc.compute_day_record(proc, [DS], "2026-10-28")
    child = dc.compute_day_isolated(proc, [DS], "2026-10-28")
    assert inproc and child and set(inproc) == set(child)
    assert {k for k in inproc if not _same(inproc[k], child[k])} == set()
    assert "LongestInactivityHours" in inproc and "C9_F1_CrisisLineHits" in inproc  # base + criteria


def test_update_writes_the_cache_and_skips_unchanged_days(data):
    proc, cache = data
    msgs = []
    df = dc.update_feature_cache(proc, cache, [DS], progress=msgs.append)
    assert list(df["Date"].dt.strftime("%Y-%m-%d")) == ["2026-10-27", "2026-10-28"]
    assert sum(m.startswith("Computing") for m in msgs) == 2
    path = dc.cache_path(cache, [DS])
    assert path.is_file() and "Fingerprint" in pd.read_csv(path, nrows=0).columns

    msgs.clear()
    again = dc.update_feature_cache(proc, cache, [DS], progress=msgs.append)
    assert not any(m.startswith("Computing") for m in msgs)  # nothing changed: all from the file
    assert len(again) == 2


def test_only_the_changed_day_is_recomputed(data):
    proc, cache = data
    dc.update_feature_cache(proc, cache, [DS])
    p = _write_partition(proc, "2026-10-28", 22, 3)  # the live ingest adds a partition
    os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 5))
    msgs = []
    dc.update_feature_cache(proc, cache, [DS], progress=msgs.append)
    assert [m for m in msgs if m.startswith("Computing")] == ["Computing day 1 of 1: 2026-10-28"]


def test_cache_is_saved_after_every_day(data, monkeypatch):
    """A crash on a later day keeps the days already computed."""
    proc, cache = data
    real = dc.compute_day_isolated

    def crash_on_second(processed_dir, base_names, day, history_rows=None, timeout=None):
        if pd.to_datetime(day).day == 28:
            raise RuntimeError("killed")
        return real(processed_dir, base_names, day, history_rows)

    monkeypatch.setattr(dc, "compute_day_isolated", crash_on_second)
    with pytest.raises(RuntimeError):
        dc.update_feature_cache(proc, cache, [DS])
    saved = pd.read_csv(dc.cache_path(cache, [DS]), parse_dates=["Date"])
    assert list(saved["Date"].dt.strftime("%Y-%m-%d")) == ["2026-10-27"]


def test_history_reaches_the_second_day(data, monkeypatch):
    proc, cache = data
    seen = []
    real = dc.compute_day_isolated

    def spy(processed_dir, base_names, day, history_rows=None, timeout=None):
        seen.append(len(history_rows or []))
        return real(processed_dir, base_names, day, history_rows)

    monkeypatch.setattr(dc, "compute_day_isolated", spy)
    dc.update_feature_cache(proc, cache, [DS])
    assert seen == [0, 1]


def test_command_line(data, capsys):
    proc, cache = data
    assert dc.main(["--dataset", DS, "--processed-dir", str(proc), "--cache-dir", str(cache)]) == 0
    assert "2 day(s)" in capsys.readouterr().out
    assert dc.cache_path(cache, [DS]).is_file()
