"""Crisis and similar sites as visits (not packets), and plain metric names (v3 review)."""

from datetime import date

import pandas as pd

from cmn_frontend import metric_names, observed
from cmn_frontend.daily import site_visits


def test_packets_are_joined_into_visits():
    ts = pd.to_datetime(["2026-11-14 12:00:00", "2026-11-14 23:40:00", "2026-11-14 23:41:30",
                         "2026-11-14 23:58:00", "2026-11-14 23:59:30"])
    df = pd.DataFrame({"Timestamp": ts, "SLD": ["x.ch", "143.ch", "143.ch", "143.ch", "143.ch"]})
    out = site_visits(df, date(2026, 11, 14), {"crisis": frozenset({"143.ch"}), "therapy": frozenset({"t.ch"})})
    assert out == {"crisis": {"visits": 2, "starts": ["23:40", "23:58"], "minutes": 4}}   # 2 + 2 min
    assert site_visits(pd.DataFrame(columns=["Timestamp", "SLD"]), date(2026, 11, 14), {"crisis": frozenset()}) == {}


def test_sensitive_item_and_text_use_visits():
    item = observed._sensitive_item("C9_F1_CrisisLineHits", "Crisis-line sites", 1098.0,
                                    {"crisis": {"visits": 2, "starts": ["23:40", "23:58"], "minutes": 4}})
    assert item["visits"] == 2 and item["value"] == 1098.0
    assert observed._visit_text(item) == "crisis-line sites 2 visits (23:40, 23:58), about 4 min"
    # without visit data (old cache) the name alone, never a packet count
    assert observed._visit_text(observed._sensitive_item("C9_F1_CrisisLineHits", "Crisis-line sites", 1098.0, {})) \
        == "crisis-line sites"


def test_metric_names_are_plain_and_never_codes():
    assert metric_names.plain("C9_F1_CrisisLineHits") == "Crisis-line sites"
    assert metric_names.plain("C4_F9_SomeNewMetricMin") == "Some new metric (min)"
    for code, name in metric_names.PLAIN.items():
        assert code not in name and "_" not in name
