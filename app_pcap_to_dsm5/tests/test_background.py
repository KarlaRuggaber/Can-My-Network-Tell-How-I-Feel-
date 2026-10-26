"""Machine background (BACKGROUND_HOST_PATTERNS, 26.10) is dropped before the features.

Run from app_pcap_to_dsm5/:  python -m pytest tests
"""

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from metrics.base_features import compute_daily_base_record  # noqa: E402
from metrics.common import background_mask, drop_background, enrich_with_hostnames  # noqa: E402

CLIENT, GATEWAY = "10.42.1.31", "10.42.1.1"
RUNNER_BACKGROUND = Path(__file__).resolve().parents[2] / "traffic-runner" / "config" / "background.yaml"


def _host_rows(host):
    e = enrich_with_hostnames(pd.DataFrame([
        {"Source IP": GATEWAY, "Destination IP": CLIENT, "IsDNS": True, "DNS_QNAME": host,
         "DNS_ANS_NAME": host, "DNS_ANS_IPS": "142.250.1.5", "Length": 100},
        {"Source IP": CLIENT, "Destination IP": "142.250.1.5", "IsDNS": False, "Length": 100},
        {"Source IP": "142.250.1.5", "Destination IP": CLIENT, "IsDNS": False, "Length": 1400},
    ]))
    return background_mask(e).tolist()


@pytest.mark.parametrize("host", [
    # the background hosts of the thesis ONU captures
    "clients2.google.com", "v10.events.data.microsoft.com", "functional.events.data.microsoft.com",
    "safebrowsing.googleapis.com", "sb-ssl.google.com", "download.windowsupdate.com",
    "fe2cr.update.microsoft.com", "ocsp.digicert.com", "cn.pool.ntp.org", "r1---sn-ni57rn7d.gvt1.com",
    # other always-on housekeeping
    "mtalk.google.com", "connectivitycheck.gstatic.com", "www.msftconnecttest.com",
    "1-courier.push.apple.com", "ocsp.pki.goog", "r3.o.lencr.org", "OCSP.Digicert.com.",
])
def test_background_hosts_are_dropped_with_their_dns_rows(host):
    assert _host_rows(host) == [True, True, True]


@pytest.mark.parametrize("host", [
    "www.google.com", "docs.google.com", "accounts.google.com", "login.live.com",  # user activity, logins
    "galleryapi.micloud.xiaomi.net", "www.icloud.com",                           # cloud sync: C7_F8/C9_F8
    "github.com", "www.srf.ch", "srf-vod-amd.akamaized.net",
    "update.microsoft.com.evil.example", "ocspapp.example.com", "mtalk.google.com.evil.example",
])
def test_user_and_lookalike_hosts_stay(host):
    assert _host_rows(host) == [False, False, False]


def test_packets_without_a_known_host_stay():
    df = pd.DataFrame({"ResolvedHost": [None, "clients2.google.com", None]})
    assert drop_background(df).index.tolist() == [0, 2]


def _runner_hosts():
    text = RUNNER_BACKGROUND.read_text(encoding="utf-8")
    hosts = re.findall(r'url: "https?://([^/":]+)', text) + re.findall(r"host: ([A-Za-z0-9.-]+)", text)
    return sorted(set(hosts))


@pytest.mark.skipif(not RUNNER_BACKGROUND.exists(), reason="traffic-runner not checked out")
def test_every_runner_background_host_is_filtered():
    """The runner's background traffic (traffic-runner/config/background.yaml) must never
    count as user activity, so every host it contacts is in the app's list."""
    hosts = _runner_hosts()
    assert len(hosts) >= 10
    df = pd.DataFrame({"ResolvedHost": hosts})
    assert dict(zip(hosts, background_mask(df))) == {h: True for h in hosts}


def _night_with_background(minutes_between=10):
    """User active until 00:30 and from 07:30 to 23:00; background every few minutes around the clock."""
    day = pd.Timestamp("2026-10-25")
    rows, ip_user, ip_bg = [], "151.101.1.7", "142.250.1.5"
    for host, ip in (("www.srf.ch", ip_user), ("v10.events.data.microsoft.com", ip_bg)):
        rows.append({"Timestamp": day, "Source IP": GATEWAY, "Destination IP": CLIENT, "IsDNS": True,
                     "DNS_QNAME": host, "DNS_ANS_NAME": host, "DNS_ANS_IPS": ip, "Length": 100})
    user = list(pd.date_range(day, day + pd.Timedelta("00:30:00"), freq="20s"))
    user += list(pd.date_range(day + pd.Timedelta("07:30:00"), day + pd.Timedelta("23:00:00"), freq="20s"))
    bg = list(pd.date_range(day + pd.Timedelta("00:03:00"), day + pd.Timedelta("23:59:00"), freq=f"{minutes_between}min"))
    for ts, ip in [(t, ip_user) for t in user] + [(t, ip_bg) for t in bg]:
        rows.append({"Timestamp": ts, "Source IP": CLIENT, "Destination IP": ip, "IsDNS": False,
                     "Protocol": "TCP", "Length": 120})
    return enrich_with_hostnames(pd.DataFrame(rows))


def test_sleep_and_timing_features_ignore_background():
    df = _night_with_background()
    raw = compute_daily_base_record(df)
    clean = compute_daily_base_record(drop_background(df))
    # with the background, the night looks awake: no quiet hours, active minutes 00-06
    assert raw["LongestInactivityHours"] < 0.2 and raw["ActiveNightMinutes"] >= 30
    # without it, the night is the 7 h quiet period from 00:30 to 07:30
    assert clean["LongestInactivityHours"] == pytest.approx(7.0, abs=0.01)
    assert clean["ActiveNightMinutes"] == 31  # 00:00-00:30 only
    assert raw["ActiveNightMinutes"] == 31 + 33  # plus one background minute every 10 min until 06:00
    assert clean["ActiveDayMinutes"] == raw["ActiveDayMinutes"] == 13 * 60  # 08:00-21:00, unchanged
