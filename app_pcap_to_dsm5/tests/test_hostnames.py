"""enrich_with_hostnames: inbound packets get the hostname of their remote (source) side.

Run from app_pcap_to_dsm5/:  python -m pytest tests
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from metrics.common import STREAMING_SLDS, enrich_with_hostnames, streaming_inbound_mask  # noqa: E402

CLIENT, GATEWAY, SERVER = "10.42.1.11", "10.42.1.1", "151.101.1.1"


def _row(src, dst, **extra):
    return {"Source IP": src, "Destination IP": dst, "IsDNS": False, "Length": 100, **extra}


def _dns_answer():
    return _row(GATEWAY, CLIENT, IsDNS=True, DNS_QNAME="www.nzz.ch", DNS_ANS_NAME="www.nzz.ch", DNS_ANS_IPS=SERVER)


def test_outbound_and_inbound_get_the_server_hostname():
    df = pd.DataFrame([_dns_answer(), _row(CLIENT, SERVER), _row(SERVER, CLIENT)])
    out = enrich_with_hostnames(df)
    assert out.loc[1, "ResolvedHost"] == "www.nzz.ch"  # client -> server
    assert out.loc[2, "ResolvedHost"] == "www.nzz.ch"  # server -> client (was None before the fix)
    assert out.loc[2, "SLD"] == "nzz.ch"


def test_dns_rows_keep_their_own_name():
    out = enrich_with_hostnames(pd.DataFrame([_dns_answer()]))
    assert out.loc[0, "ResolvedHost"] == "www.nzz.ch"


def test_public_to_public_still_uses_destination():
    # ISP-side captures (thesis ONU data) have no private client: behaviour unchanged.
    other = "8.8.8.8"
    dns = _row(other, SERVER, IsDNS=True, DNS_QNAME="www.nzz.ch", DNS_ANS_NAME="www.nzz.ch", DNS_ANS_IPS=SERVER)
    out = enrich_with_hostnames(pd.DataFrame([dns, _row(SERVER, other)]))
    assert pd.isna(out.loc[1, "ResolvedHost"])  # destination 8.8.8.8 is unknown, as before


def test_without_source_ip_column_falls_back_to_destination():
    df = pd.DataFrame([_dns_answer(), _row(CLIENT, SERVER)]).drop(columns=["Source IP"])
    out = enrich_with_hostnames(df)
    assert out.loc[1, "ResolvedHost"] == "www.nzz.ch"


# --- broadcaster VOD hosts (SERVICE_HOSTS, 25.10) ------------------------------------------------

VOD = "151.101.2.2"


def _stream_rows(host):
    dns = _row(GATEWAY, CLIENT, IsDNS=True, DNS_QNAME=host, DNS_ANS_NAME=host, DNS_ANS_IPS=VOD)
    return pd.DataFrame([dns, _row(CLIENT, VOD, **{"Source Port": 50000, "Destination Port": 443}),
                         _row(VOD, CLIENT, **{"Source Port": 443, "Destination Port": 50000, "Length": 1400})])


def test_srf_vod_host_counts_as_srf_streaming():
    out = enrich_with_hostnames(_stream_rows("srf-vod-amd.akamaized.net"))
    assert out.loc[2, "ResolvedHost"] == "srf-vod-amd.akamaized.net"  # real host kept for tracing
    assert out.loc[2, "SLD"] == "srf.ch" and "srf.ch" in STREAMING_SLDS
    assert bool(streaming_inbound_mask(out).loc[2])  # the downstream packet counts as streaming


@pytest.mark.parametrize("host", [
    "colibri-js.akamaized.net",                  # SRF's scripts on the same CDN: not video
    "images.akamaized.net",                      # other sites on Akamai
    "srf-vod-amd.akamaized.net.evil.example",    # lookalike
    "xsrf-vod-amd.akamaized.net",
    "srf-vod-amd.akamaihd.net",                  # other CDN domain: only add when measured
])
def test_other_cdn_hosts_keep_their_sld(host):
    out = enrich_with_hostnames(_stream_rows(host))
    assert out.loc[2, "SLD"] != "srf.ch"
    assert not bool(streaming_inbound_mask(out).loc[2])
