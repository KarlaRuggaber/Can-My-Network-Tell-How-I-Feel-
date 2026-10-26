"""C2_F6 productivity hits: shared domains (google.com, microsoft.com, live.com) count only their
productivity hosts (PRODUCTIVITY_SHARED_HOSTS, 26.10). Run from app_pcap_to_dsm5/: python -m pytest tests
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from metrics.common import enrich_with_hostnames, productivity_mask  # noqa: E402
from metrics.criterion2 import _productivity_hits  # noqa: E402

CLIENT, GATEWAY, SERVER = "10.42.1.31", "10.42.1.1", "142.250.1.1"


def _counted(host):
    """One DNS answer for `host`, then one outbound and one inbound packet to its IP."""
    dns = {"Source IP": GATEWAY, "Destination IP": CLIENT, "IsDNS": True, "DNS_QNAME": host,
           "DNS_ANS_NAME": host, "DNS_ANS_IPS": SERVER, "Length": 100}
    out = {"Source IP": CLIENT, "Destination IP": SERVER, "IsDNS": False, "Length": 100}
    inn = {"Source IP": SERVER, "Destination IP": CLIENT, "IsDNS": False, "Length": 1400}
    e = enrich_with_hostnames(pd.DataFrame([dns, out, inn]))
    return productivity_mask(e).tolist()[1:]  # the two data packets


@pytest.mark.parametrize("host", [
    "docs.google.com", "drive.google.com", "mail.google.com", "calendar.google.com",
    "meet.google.com", "scholar.google.com",                       # Google tools, scholar for study
    "teams.microsoft.com", "www.microsoft.com",                    # www: runner's Office stand-in
    "outlook.live.com",
    "github.com", "about.gitlab.com", "trello.com", "outlook.office.com", "www.office.com",  # unchanged
])
def test_productivity_hosts_count(host):
    assert _counted(host) == [True, True]


@pytest.mark.parametrize("host", [
    # the background hosts behind the 11 932 hits of a day without any work (25.10)
    "www.google.com", "accounts.google.com", "news.google.com", "region1.analytics.google.com",
    "play.google.com", "stun.l.google.com", "marketingplatform.google.com", "pay.google.com",
    "fundingchoicesmessages.google.com", "google.com",
    "adsdk.microsoft.com", "login.live.com",
    "docs.google.com.evil.example", "docsgoogle.com",              # lookalikes
])
def test_background_and_lookalike_hosts_do_not_count(host):
    assert _counted(host) == [False, False]


def test_hits_of_a_mixed_day():
    rows = []
    for i, host in enumerate(["docs.google.com", "www.google.com", "github.com", "stun.l.google.com"]):
        ip = f"142.250.1.{i + 1}"
        rows.append({"Source IP": GATEWAY, "Destination IP": CLIENT, "IsDNS": True, "DNS_QNAME": host,
                     "DNS_ANS_NAME": host, "DNS_ANS_IPS": ip, "Length": 100})
        rows += [{"Source IP": CLIENT, "Destination IP": ip, "IsDNS": False, "Length": 100}] * 3
    e = enrich_with_hostnames(pd.DataFrame(rows))
    # docs.google.com and github.com: their DNS answer row + 3 packets each (DNS rows counted as before)
    assert _productivity_hits(e) == 8.0


def test_without_resolved_host_only_plain_domains_count():
    df = pd.DataFrame({"SLD": ["github.com", "google.com", None]})
    assert productivity_mask(df).tolist() == [True, False, False]
