"""enrich_with_hostnames: per client and time (the latest DNS answer the client received for
the IP before the packet), since 27.10. Run from app_pcap_to_dsm5/:  python -m pytest tests
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from metrics import common  # noqa: E402
from metrics.common import background_mask, dns_answers, enrich_with_hostnames  # noqa: E402

GATEWAY, PHONE, LAPTOP = "10.42.1.1", "10.42.1.21", "10.42.1.22"
GOOGLE = "74.125.29.100"  # served google.com by day and clients2.google.com at night (27.10)
T = pd.Timestamp("2026-10-26")


def at_(text):
    """'10:27', '1 days 01:00:01.050' -> timestamp on 26.10 (+ days)."""
    days, _, clock = text.rpartition(" days ")
    clock = clock if clock.count(":") == 2 else clock + ":00"
    return T + pd.Timedelta(days=int(days or 0)) + pd.Timedelta(clock)


def answer(at, client, name, ips):
    return {"Timestamp": at_(at), "Source IP": GATEWAY, "Destination IP": client,
            "IsDNS": True, "DNS_QNAME": None, "DNS_ANS_NAME": name, "DNS_ANS_IPS": ips, "Length": 120}


def packet(at, src, dst):
    return {"Timestamp": at_(at), "Source IP": src, "Destination IP": dst,
            "IsDNS": False, "Length": 100}


def hosts(rows):
    e = enrich_with_hostnames(pd.DataFrame(rows))
    return e.loc[~e["IsDNS"], "ResolvedHost"].tolist(), e


def test_shared_ip_gets_the_name_of_the_latest_answer():
    got, e = hosts([
        answer("10:27", LAPTOP, "google.com", GOOGLE),
        packet("10:28", LAPTOP, GOOGLE),
        answer("1 days 01:00", LAPTOP, "clients2.google.com", GOOGLE),
        packet("1 days 01:00:01", LAPTOP, GOOGLE),
        packet("1 days 01:00:01.050", GOOGLE, LAPTOP),  # the answer of the server (inbound)
    ])
    assert got == ["google.com", "clients2.google.com", "clients2.google.com"]
    # the night request is now recognised as background; the day visit is not
    assert background_mask(e[~e["IsDNS"]]).tolist() == [False, True, True]


def test_each_client_uses_its_own_answers():
    got, _ = hosts([
        answer("09:00", PHONE, "www.gstatic.com", "74.125.29.94"),
        answer("09:05", LAPTOP, "ocsp.pki.goog", "74.125.29.94"),
        packet("09:10", PHONE, "74.125.29.94"),
        packet("09:10", LAPTOP, "74.125.29.94"),
    ])
    assert got == ["www.gstatic.com", "ocsp.pki.goog"]


def test_without_an_earlier_answer_the_day_map_is_the_fallback():
    # a connection the phone opened before the capture started: only a later answer exists
    got, _ = hosts([
        packet("08:00", PHONE, "2.16.168.46"),
        answer("09:00", LAPTOP, "www.msftconnecttest.com", "2.16.168.46"),
        packet("10:00", "203.0.113.200", "8.8.4.4"),  # never answered: stays unknown
    ])
    assert got[0] == "www.msftconnecttest.com" and pd.isna(got[1])


def test_row_order_and_index_are_kept():
    rows = [
        packet("1 days 01:00:01", LAPTOP, GOOGLE),
        answer("1 days 01:00", LAPTOP, "clients2.google.com", GOOGLE),
        packet("10:28", LAPTOP, GOOGLE),
        answer("10:27", LAPTOP, "google.com", GOOGLE),
    ]
    df = pd.DataFrame(rows, index=[40, 10, 30, 20])
    e = enrich_with_hostnames(df)
    assert e.index.tolist() == [40, 10, 30, 20]
    assert e.loc[[40, 30], "ResolvedHost"].tolist() == ["clients2.google.com", "google.com"]


def test_cname_tokens_and_ipv6_in_answers():
    a = dns_answers(pd.DataFrame([answer(
        "08:49", LAPTOP, "fe2cr.update.microsoft.com",
        "b'fe2cr.update.msft.com.trafficmanager.net.',172.184.231.75,2603:1030:10:15::626")]))
    assert a["ip"].tolist() == ["172.184.231.75", "2603:1030:10:15::626"]
    assert set(a["name"]) == {"fe2cr.update.microsoft.com"} and set(a["client"]) == {LAPTOP}


def test_data_without_timestamps_keeps_the_day_map():
    rows = [answer("10:27", LAPTOP, "google.com", GOOGLE), answer("11:00", LAPTOP, "clients2.google.com", GOOGLE),
            packet("11:01", LAPTOP, GOOGLE)]
    df = pd.DataFrame(rows).drop(columns="Timestamp")
    e = enrich_with_hostnames(df)
    assert e["ResolvedHost"].tolist()[-1] == "google.com"  # first answer wins, as before


def test_chunked_join_gives_the_same_names(monkeypatch):
    rows = []
    for h in range(20):  # the IP changes its name every hour, packets in between
        rows.append(answer(f"{h:02d}:00", LAPTOP if h % 2 else PHONE, f"host{h}.example.com", GOOGLE))
        rows += [packet(f"{h:02d}:{m:02d}:30", LAPTOP if h % 2 else PHONE, GOOGLE) for m in range(0, 60, 7)]
    df = pd.DataFrame(rows).sample(frac=1, random_state=3)
    whole = enrich_with_hostnames(df)["ResolvedHost"]
    monkeypatch.setattr(common, "TIMED_CHUNK", 7)
    chunked = enrich_with_hostnames(df)["ResolvedHost"]
    assert whole.equals(chunked)
    pk = whole[~df["IsDNS"]]
    hours = pd.to_datetime(df.loc[~df["IsDNS"], "Timestamp"]).dt.hour
    assert (pk == "host" + hours.astype(str) + ".example.com").all()
