"""Evaluation tests: effect size and verdicts, the page's scoring functions, the gate, the day loop."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from evaluation import compare, daily, scoring


def test_cliffs_delta():
    assert compare.cliffs_delta([5, 6, 7], [1, 2, 3]) == 1.0
    assert compare.cliffs_delta([1, 2, 3], [5, 6, 7]) == -1.0
    assert compare.cliffs_delta([1, 2], [1, 2]) == 0.0
    assert compare.cliffs_delta([np.nan], [1]) is None
    assert compare.direction(0.33) == "up" and compare.direction(-0.5) == "down"
    assert compare.direction(0.2) == "no change" and compare.direction(None) == "n/a"


def _daily(metric: str, base: list[float], prof: list[float]) -> pd.DataFrame:
    rows = [{"Date": pd.Timestamp("2026-10-26") + pd.Timedelta(days=i), "phase": "baseline", metric: v}
            for i, v in enumerate(base)]
    rows += [{"Date": pd.Timestamp("2026-11-09") + pd.Timedelta(days=i), "phase": "profile", metric: v}
             for i, v in enumerate(prof)]
    return pd.DataFrame(rows)


@pytest.mark.parametrize("expected, base, prof, verdict", [
    ("up", [1, 2, 3, 2], [5, 6, 7], "as expected"),
    ("up", [5, 6, 7], [1, 2, 3], "opposite"),
    ("down", [5, 6, 7], [1, 2, 3], "as expected"),
    ("up", [1, 2, 3], [2, 2, 2], "no change"),
    ("unchanged", [1, 2, 3], [2, 2, 2], "unchanged (ok)"),
    ("unchanged", [1, 2, 3], [9, 9, 9], "changed up (expected none)"),
])
def test_verdicts(expected, base, prof, verdict):
    df = _daily("M", base, prof)
    exp = {"metrics": {"M": expected}} if expected != "unchanged" else {"unchanged": ["M"]}
    (row,) = compare.compare_metrics(df, exp)
    assert row.verdict == verdict
    assert row.n_base == len(base) and row.n_prof == len(prof)


def test_missing_metric_is_reported():
    (row,) = compare.compare_metrics(_daily("M", [1], [2]), {"metrics": {"X": "up"}})
    assert row.verdict == "metric missing"


def test_page_functions_are_loaded_from_the_page_source():
    cfg = scoring.load_config(scoring.APP_DIR / "fasl_config.json")
    fn = scoring.load_page_functions(cfg)
    assert set(fn) == set(scoring.FUNCTIONS)
    # thesis shape mid = hi: values at or above hi score 0 (thesis-alignment §4)
    assert fn["mf_tri"](50, 20, 80, 80) == 0.5
    assert fn["mf_tri"](80, 20, 80, 80) == 0.0
    # one-sided, open upper end
    assert fn["mf_tri"](5000, 20, 80, 1e9) == pytest.approx(1.0, abs=1e-4)
    assert fn["gate_present"](pd.Series([0.7] * 6 + [0.1] * 8), theta=0.6, need_days=6, window=14)
    assert not fn["gate_present"](pd.Series([0.7] * 5 + [0.1] * 9), theta=0.6, need_days=6, window=14)


def test_likelihoods_and_episode():
    cfg = {"M": 14, "N": 6, "theta": 0.6, "tau": 1.0, "core_symptoms": ["C2"],
           **{c: {f"{c}_X": {"w": 1.0, "mf": {"type": "tri", "lo": 0, "mid": 10, "hi": 1e9}}}
              for c in scoring.CRIT_KEYS}}
    days = pd.DataFrame({"Date": pd.date_range("2026-11-09", periods=14),
                         **{f"{c}_X": [20.0] * 14 for c in scoring.CRIT_KEYS[:5]},
                         **{f"{c}_X": [0.0] * 14 for c in scoring.CRIT_KEYS[5:]}})
    lk = scoring.likelihoods(days, cfg)
    assert lk["L_C1"].tolist() == pytest.approx([1.0] * 14) and lk["L_C9"].tolist() == [0.0] * 14
    g = scoring.gate(lk, cfg)
    assert g["total_present"] == 5 and g["core_present"] and g["episode"]
    cfg["core_symptoms"] = ["C7"]
    assert not scoring.gate(lk, cfg)["episode"]


def test_day_loop_on_a_tiny_dataset(tmp_path):
    """Two partitions on two days; each day only sees its own packets and the earlier days as history."""
    ds = tmp_path / "gw_test_a"
    ds.mkdir()
    for day, n in (("20261109", 50), ("20261110", 80)):
        ts = pd.date_range(f"{day[:4]}-{day[4:6]}-{day[6:]} 10:00", periods=n, freq="10s")
        pd.DataFrame({
            "Timestamp": ts, "Date": ts.date, "Hour": ts.hour, "Protocol": "TCP",
            "Source IP": "10.42.1.21", "Destination IP": "93.184.216.34", "Source Port": 50000,
            "Destination Port": 443, "TCP Flags": "PA", "Length": 1000, "IsDNS": False,
            "DNS_QNAME": None, "DNS_QTYPE": None, "DNS_ANS_NAME": None, "DNS_ANS_IPS": None,
        }).to_parquet(ds / f"gw_test_a__{day}_1000.parquet")
    table, errors = daily.compute_dataset(ds, log=lambda *_: None)
    assert table["Date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-11-09", "2026-11-10"]
    assert "C2_F1_UniqueSLD" in table.columns
