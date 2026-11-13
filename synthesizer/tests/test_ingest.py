"""Acceptance: the unchanged ingest (app_pcap_to_dsm5/ingest/tapingest.py --once) takes the synthetic output like a
live capture. Needs scapy, pandas and pyarrow (app_pcap_to_dsm5/ingest/requirements.txt); skipped without them."""

from __future__ import annotations

import csv
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

pytest.importorskip("scapy")
pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

from fixtures import GW_IP, GW_MAC, REC, dns_answer, dns_query, eth, make_recording, plan_row, tcp, udp, write_plan  # noqa: E402
from synthesizer import library  # noqa: E402
from synthesizer.build import build  # noqa: E402
from synthesizer.trace import trace  # noqa: E402
from synthesizer.rewrite import Rewriter, port_shift  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "app_pcap_to_dsm5"
TZ = ZoneInfo("Europe/Zurich")
sys.path.insert(0, str(APP / "app"))
from utils.pcap_etl import parse_packet_row  # noqa: E402
from scapy.layers.l2 import Ether  # noqa: E402

SAME_FIELDS = ["Protocol", "TCP Flags", "Length", "IsDNS", "DNS_QNAME", "DNS_QTYPE", "DNS_ANS_NAME", "DNS_ANS_IPS"]


def test_rewrite_keeps_every_ingest_field_but_the_client():
    ip, mac = REC["rec_a_phone"]
    frames = [eth(mac, GW_MAC, udp(ip, GW_IP, 51000, 53, dns_query("www.nzz.ch"))),
              eth(GW_MAC, mac, udp(GW_IP, ip, 53, 51000, dns_answer("www.nzz.ch", "203.0.113.5"))),
              eth(mac, GW_MAC, tcp(ip, "203.0.113.5", 40000, 443, ck="partial")),
              eth(GW_MAC, mac, tcp("203.0.113.5", ip, 443, 40000))]
    rw = Rewriter(ip, "10.42.1.21", mac, "02:00:0a:2a:01:15")
    for f in frames:
        a = Ether(f)
        a.time = 1_792_764_000.5
        b = Ether(rw.apply(f, port_shift(2)))
        b.time = 1_792_764_000.5
        ra, rb = parse_packet_row(a), parse_packet_row(b)
        assert {k: ra.get(k) for k in SAME_FIELDS} == {k: rb.get(k) for k in SAME_FIELDS}
        assert {ra["Source IP"], ra["Destination IP"]} - {ip} == {rb["Source IP"], rb["Destination IP"]} - {"10.42.1.21"}
    assert parse_packet_row(Ether(rw.apply(frames[1])))["DNS_ANS_IPS"] == "203.0.113.5"


def test_ingest_accepts_a_synthetic_day(tmp_path):
    make_recording(tmp_path, datetime(2026, 10, 23, 16, 0, tzinfo=TZ))
    lib = tmp_path / "library"
    library.cut(tmp_path / "ground_truth.csv", [tmp_path / "ready"], library.load_devices(tmp_path / "devices.csv"),
                lib, log=lambda *_: None)
    day = datetime(2026, 10, 25, tzinfo=TZ)   # DST day: 25 hours
    at = lambda h, m=0: datetime.fromisoformat(f"2026-10-25T{h:02d}:{m:02d}:00").replace(tzinfo=TZ)
    rows = [plan_row(datetime.fromisoformat("2026-10-25T02:40:00+02:00"), 600, "tgt_a_phone", "phone_check",
                     "20261024-night-01", "social_passive:1", day="2026-10-24"),
            plan_row(at(9), 400, "tgt_a_phone", "phone_check", "20261025-wake_check-01", "news:1"),
            plan_row(at(10), 1200, "tgt_a_laptop", "video_stream", "20261025-stream-01", "streaming:1"),
            plan_row(at(20), 900, "tgt_a_laptop", "gaming_session", "20261025-gaming-01", "gaming:1"),
            plan_row(at(20), 900, "tgt_a_laptop", "voice_call", "20261025-gaming-01-voice",
                     companion_of="20261025-gaming-01")]
    assert day.date().isoformat() == "2026-10-25"
    write_plan(tmp_path / "plan.csv", rows)
    out = tmp_path / "syn_tgt_b"
    summary = build(tmp_path / "plan.csv", lib, tmp_path / "devices.csv", "syn_tgt_b", out, log=lambda *_: None)
    assert summary["packets"] > 0

    parquet = tmp_path / "processed_parquet"
    env = dict(os.environ, TZ="Europe/Zurich")
    r = subprocess.run([sys.executable, str(APP / "ingest" / "tapingest.py"), "--watch", str(out / "ready"),
                        "--devices", str(out / "devices.csv"), "--out", str(parquet),
                        "--state", str(tmp_path / "state.sqlite"), "--once"],
                       env=env, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in parquet.iterdir() if p.is_dir()) == ["syn_tgt_b"]   # nothing unassigned

    df = pd.concat([pd.read_parquet(p) for p in (parquet / "syn_tgt_b").glob("*.parquet")])
    assert len(df) == summary["packets"]              # fixture traffic has no background to filter
    assert set(df["Capture File"]) == {p.name for p in (out / "ready").iterdir()}
    assert set(df.loc[df["IsDNS"] & df["DNS_QNAME"].notna(), "DNS_QNAME"]) >= {"www.20min.ch", "www.youtube.com"}
    # the night block before the switch is at 02:40 summer time; Parquet holds naive local time
    night = df[df["Timestamp"].dt.strftime("%Y-%m-%d %H") == "2026-10-25 02"]
    assert len(night) > 0

    counts, stats = trace(out, parquet / "syn_tgt_b")
    assert stats["untraced"] == 0
    manifest = {m["block_id"]: m for m in csv.DictReader(open(out / "manifest.csv"))}
    for c in counts:
        if c["block_id"] == "20261024-night-01":
            continue  # its time is in the repeated hour: ambiguous in naive local time
        assert c["missing"] == 0, c
    assert stats["dst_ambiguous"] == int(manifest["20261024-night-01"]["packets"])
