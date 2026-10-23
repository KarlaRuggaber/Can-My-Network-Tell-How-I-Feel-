"""Tests for the synthesizer (stdlib only; the ingest tests are in test_ingest.py)."""

from __future__ import annotations

import csv
import json
import random
import struct
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from fixtures import (GW_IP, GW_MAC, REC, dns_answer, dns_query, eth, make_recording, plan_row, tcp, udp,
                      write_plan)
from synthesizer import catalog, cli, library
from synthesizer.build import build, check_dataset, coverage
from synthesizer.catalog import S
from synthesizer.pcap import PcapWriter, iter_packets
from synthesizer.rewrite import (Rewriter, _fold, _sum16, csum_update, ip_header_valid, l4_checksum_valid,
                                 port_shift)
from synthesizer.select import Snippet, candidates

TZ = ZoneInfo("Europe/Zurich")
PHONE_IP, PHONE_MAC = REC["rec_a_phone"]
SERVER = "203.0.113.5"


# -------------------- pcap --------------------

def test_pcap_roundtrip(tmp_path):
    p = tmp_path / "a.pcap"
    with PcapWriter(p) as w:
        w.write(1_792_764_000_387_123, 100, b"\x01" * 60)
        w.write(1_792_764_001_000_000, 60, b"\x02" * 60)
    got = list(iter_packets(p))
    assert got == [(1_792_764_000_387_123, 100, b"\x01" * 60), (1_792_764_001_000_000, 60, b"\x02" * 60)]
    assert p.read_bytes()[:4] == bytes.fromhex("d4c3b2a1")   # same magic as tapcap


def test_pcap_reads_nanosecond_files(tmp_path):
    p = tmp_path / "ns.pcap"
    p.write_bytes(struct.pack("<IHHiIII", 0xA1B23C4D, 2, 4, 0, 0, 65535, 1)
                  + struct.pack("<IIII", 10, 123_456_789, 4, 4) + b"abcd")
    assert list(iter_packets(p)) == [(10_123_456, 4, b"abcd")]


def test_pcap_truncated_last_record_is_ignored(tmp_path):
    p = tmp_path / "t.pcap"
    with PcapWriter(p) as w:
        w.write(S, 10, b"\x00" * 10)
    p.write_bytes(p.read_bytes() + struct.pack("<IIII", 2, 0, 100, 100) + b"\x00" * 5)
    assert len(list(iter_packets(p))) == 1


# -------------------- rewrite --------------------

def test_csum_update_matches_full_recompute():
    rng = random.Random(1)
    for _ in range(200):
        data = bytes(rng.randrange(256) for _ in range(40))
        ck = ~_sum16(data) & 0xFFFF
        new = bytearray(data)
        new[12:16] = bytes(rng.randrange(256) for _ in range(4))
        assert csum_update(ck, data[12:16], bytes(new[12:16])) == ~_sum16(bytes(new)) & 0xFFFF \
            or _sum16(bytes(new)) == 0xFFFF   # ±0 ambiguity of one's complement


@pytest.mark.parametrize("mk", [
    lambda: eth(PHONE_MAC, GW_MAC, tcp(PHONE_IP, SERVER, 40000, 443)),
    lambda: eth(GW_MAC, PHONE_MAC, tcp(SERVER, PHONE_IP, 443, 40000)),
    lambda: eth(PHONE_MAC, GW_MAC, udp(PHONE_IP, GW_IP, 51000, 53, dns_query("www.nzz.ch"))),
    lambda: eth(GW_MAC, PHONE_MAC, udp(GW_IP, PHONE_IP, 53, 51000, dns_answer("www.nzz.ch", SERVER))),
])
@pytest.mark.parametrize("copy", [0, 3])
def test_valid_checksums_stay_valid(mk, copy):
    f = mk()
    assert l4_checksum_valid(f) and ip_header_valid(f)
    out = Rewriter(PHONE_IP, "10.42.1.21", PHONE_MAC, "02:00:0a:2a:01:15").apply(f, port_shift(copy))
    assert l4_checksum_valid(out) and ip_header_valid(out)
    assert "10.42.1.11" not in _ips(out) and "10.42.1.21" in _ips(out)
    assert bytes.fromhex("02000a2a010b") not in out[:12] and bytes.fromhex("02000a2a0115") in out[:12]


def _ips(frame):
    return {".".join(map(str, frame[26:30])), ".".join(map(str, frame[30:34]))}


def test_partial_checksum_stays_partial():
    """br-sim records offloaded checksums (pseudo-header sum only); they must stay in that form for the new IP."""
    f = eth(PHONE_MAC, GW_MAC, tcp(PHONE_IP, SERVER, 40000, 443, ck="partial"))
    out = Rewriter(PHONE_IP, "10.42.1.21", None, None).apply(f, port_shift(2))
    ihl = 20
    total = int.from_bytes(out[16:18], "big")
    pseudo = _fold(_sum16(out[26:34]) + 6 + total - ihl)
    assert int.from_bytes(out[14 + ihl + 16:14 + ihl + 18], "big") == pseudo
    assert ip_header_valid(out)


def test_udp_without_checksum_keeps_zero():
    f = eth(PHONE_MAC, GW_MAC, udp(PHONE_IP, SERVER, 50000, 10000, ck="zero"))
    out = Rewriter(PHONE_IP, "10.42.1.21", None, None).apply(f)
    assert out[14 + 20 + 6:14 + 20 + 8] == b"\x00\x00"


def test_rewrite_keeps_servers_payload_and_length():
    f = eth(GW_MAC, PHONE_MAC, udp(GW_IP, PHONE_IP, 53, 51000, dns_answer("www.nzz.ch", SERVER)))
    out = Rewriter(PHONE_IP, "10.42.1.21", PHONE_MAC, "02:00:0a:2a:01:15").apply(f)
    assert len(out) == len(f)
    assert out[26:30] == f[26:30]                            # gateway/DNS server unchanged
    assert out[14 + 28:] == f[14 + 28:]                      # DNS message (answer IPs) untouched
    assert out[6:12] == f[6:12]                              # gateway MAC unchanged


def test_rewrite_ignores_other_hosts_and_non_ipv4():
    rw = Rewriter(PHONE_IP, "10.42.1.21", None, None)
    assert rw.apply(eth("02:00:00:00:00:01", GW_MAC, tcp("10.42.1.99", SERVER, 1, 2))) is None
    assert rw.apply(eth(PHONE_MAC, "ff:ff:ff:ff:ff:ff", b"\x00" * 28, 0x0806)) is None


def test_port_shift_is_a_bijection_and_spares_low_ports():
    for k in (1, 2, 17):
        f = port_shift(k)
        assert sorted(f(p) for p in range(1024, 65536)) == list(range(1024, 65536))
        assert all(f(p) == p for p in (53, 443, 1023))
        assert f(40000) != 40000
    assert port_shift(0)(40000) == 40000


def test_client_port_changes_only_on_client_side():
    out = Rewriter(PHONE_IP, "10.42.1.21", None, None).apply(
        eth(GW_MAC, PHONE_MAC, tcp(SERVER, PHONE_IP, 443, 40000)), port_shift(1))
    sport, dport = struct.unpack("!HH", out[34:38])
    assert sport == 443 and dport == port_shift(1)(40000)


def test_non_first_fragment_gets_only_the_ip_header_fixed():
    from fixtures import ipv4
    frag = eth(PHONE_MAC, GW_MAC, ipv4(PHONE_IP, SERVER, 17, b"z" * 40, frag=0x00B9))
    out = Rewriter(PHONE_IP, "10.42.1.21", None, None).apply(frag, port_shift(5))
    assert ip_header_valid(out) and out[34:] == frag[34:]


# -------------------- catalog --------------------

def test_categories_from_hosts():
    table = catalog.load_host_categories(None) | {"tiktok.com": {"social_passive"}, "nzz.ch": {"news"},
                                                   "gitlab.com": {"work"}}
    assert catalog.categories_of(["www.tiktok.com", "www.nzz.ch"], "phone_check", table) == ["social_passive", "news"]
    assert catalog.categories_of(["about.gitlab.com"], "work_block", table) == ["work"]
    assert catalog.categories_of(["www.reddit.com"], "social_post", table) == ["social_post"]
    assert catalog.categories_of(["peer.sim"], "voice_call", table) == ["call"]
    assert catalog.categories_of(["unknown.example"], "browse", table) == []


def test_mixes_yaml_is_readable():
    pytest.importorskip("yaml")
    table = catalog.load_host_categories(cli.DEFAULT_MIXES)
    assert "news" in table["nzz.ch"] and "audio" in table["srf.ch"]


def test_parse_mix_and_options():
    assert catalog.parse_mix("news:0.4,messaging:0.4,search:0.2") == {"news": .4, "messaging": .4, "search": .2}
    assert catalog.parse_mix("news,search") == {"news": 1.0, "search": 1.0}
    assert catalog.parse_options("mic_share=0.1") == {"mic_share": "0.1"}


# -------------------- library --------------------

@pytest.fixture
def recorded(tmp_path):
    base = datetime(2026, 10, 23, 16, 0, tzinfo=TZ)
    rec = make_recording(tmp_path, base)
    devices = library.load_devices(tmp_path / "devices.csv")
    lib = tmp_path / "library"
    try:
        import yaml  # noqa: F401  (host -> category from the runner's mixes.yaml)
        mixes = cli.DEFAULT_MIXES
    except ImportError:
        mixes = None
    library.cut(tmp_path / "ground_truth.csv", [tmp_path / "ready"], devices, lib, mixes_yaml=mixes,
                log=lambda *_: None)
    return tmp_path, lib, rec


def _index(lib):
    return {r["block_ids"].split(";")[0]: r for r in library.read_index(lib)}


def test_cut_one_snippet_per_ok_block_and_groups_companions(recorded):
    _, lib, _ = recorded
    idx = _index(lib)
    assert set(idx) == {"b-pc1", "b-pc2", "b-sp1", "b-vs1", "b-g1", "b-msg1"}   # no error/idle rows
    assert idx["b-g1"]["block_ids"] == "b-g1;b-g1-voice" and idx["b-g1"]["companions"] == "voice_call"
    assert idx["b-pc1"]["role"] == "phone" and idx["b-vs1"]["role"] == "laptop"
    for r in idx.values():
        assert (lib / "snippets" / f"{r['snippet_id']}.pcap").exists()


def test_cut_windows_tail_and_next_block(recorded):
    _, lib, _ = recorded
    idx = _index(lib)
    assert float(idx["b-pc1"]["tail_s"]) == 30            # next block at +100 s, tail 30 s
    assert float(idx["b-pc2"]["tail_s"]) == 10            # ends at 190 s, next block at 200 s
    assert float(idx["b-pc1"]["first_page_s"]) == pytest.approx(1.5)
    assert int(idx["b-pc1"]["dns_queries"]) == 2


def test_cut_keeps_only_the_device_ipv4_packets(recorded):
    _, lib, rec = recorded
    r = _index(lib)["b-pc1"]
    pkts = list(iter_packets(lib / "snippets" / f"{r['snippet_id']}.pcap"))
    assert pkts and all(PHONE_IP in _ips(d) for _, _, d in pkts)
    assert all(d[12:14] == b"\x08\x00" for _, _, d in pkts)
    t0 = library.iso_to_us(r["start"])
    assert min(t for t, _, _ in pkts) >= t0
    assert int(r["packets"]) == len(pkts)


def test_cut_is_incremental(recorded):
    tmp, lib, _ = recorded
    devices = library.load_devices(tmp / "devices.csv")
    new = library.cut(tmp / "ground_truth.csv", [tmp / "ready"], devices, lib, log=lambda *_: None)
    assert new == [] and len(library.read_index(lib)) == 6


def test_cut_with_plan_mix(recorded, tmp_path):
    tmp, _, _ = recorded
    cmds = tmp / "x.commands.tsv"
    cmds.write_text("# comment\n2026-10-23T16:00:00+02:00\t-\trec_a_phone\tb-pc1\tscripts/run-activity.sh rec_a_phone "
                    "--activity phone_check --duration 60 --mix news:0.5,messaging:0.5 --block-id b-pc1\n"
                    "2026-10-23T16:00:00+02:00\t-\trec_a_laptop\tb-g1-voice\tscripts/run-activity.sh x "
                    "--activity voice_call --mic-share 10% --block-id b-g1-voice\n")
    info = library.load_block_info([], [cmds])
    assert info["b-pc1"]["mix"] == "news:0.5,messaging:0.5" and info["b-g1-voice"]["mic_share"] == "0.1"


def test_alias_for_renamed_devices():
    d = {"student_a_phone": library.Device("student_a_phone", "phone", "02:00:0a:2a:01:0b", "10.42.1.11", "x")}
    out = library.apply_aliases(d, ["student01_phone=student_a_phone"])
    assert out["student01_phone"].ip == "10.42.1.11" and out["student01_phone"].role == "phone"
    with pytest.raises(ValueError):
        library.apply_aliases(d, ["a=b"])


def test_overlapping_blocks_on_one_device_are_ambiguous():
    us = lambda s: s * S
    gt = [{"start": "2026-10-23T16:00:00+02:00", "end": "x", "device": "d", "activity_id": "browse", "domains": "",
           "block_id": "a", "status": "ok", "start_us": us(0), "end_us": us(600)},
          {"start": "2026-10-23T16:05:00+02:00", "end": "x", "device": "d", "activity_id": "browse", "domains": "",
           "block_id": "b", "status": "ok", "start_us": us(300), "end_us": us(900)},
          {"start": "2026-10-23T16:15:00+02:00", "end": "x", "device": "d", "activity_id": "browse", "domains": "",
           "block_id": "c", "status": "ok", "start_us": us(898), "end_us": us(1000)}]
    units = library.build_units(gt)
    flags = {u.host["block_id"]: u.flags for u in units}
    assert "ambiguous" in flags["a"] and "ambiguous" in flags["b"]
    assert flags["c"] == []   # 2 s overlap with b = back to back
    assert [u.window_end_us for u in units if u.host["block_id"] == "b"] == [us(898)]


# -------------------- selection --------------------

def _snip(sid, activity="phone_check", role="phone", cats=("news",), dur=60, companions=(), **kw):
    return Snippet(sid=sid, activity=activity, companions=tuple(companions), role=role, client_ip=PHONE_IP,
                   client_mac=PHONE_MAC, start_us=0, dur_us=dur * S, tail_us=0, first_page_us=S,
                   cats=[{c} for c in cats], mic_share=kw.get("mic_share", ""), lookups=kw.get("lookups", ""),
                   flags=set(kw.get("flags", ())), path=Path("/dev/null"))


def _row(activity="phone_check", mix="news:0.4,social_passive:0.4,messaging:0.2", dur=300, **kw):
    start = datetime(2026, 11, 2, 9, 0, tzinfo=TZ)
    r = plan_row(start, dur, "tgt_a_phone", activity, "20261102-wake_check-01", mix, **kw)
    from synthesizer.select import PlanRow
    return PlanRow(raw=r, block_id=r["block_id"], device=r["device"], activity=activity,
                   start_us=round(start.timestamp() * S), end_us=round(start.timestamp() * S) + dur * S,
                   mix=catalog.parse_mix(mix), options=catalog.parse_options(r.get("options")) |
                   ({"lookups": r["lookups"]} if r.get("lookups") else {}), seed="5", companion_of="", day="")


def test_mix_compatible_snippets_weighted_by_plan_weight():
    news, social, shop = _snip("n", cats=("news",)), _snip("s", cats=("social_passive",)), _snip("x", cats=("shopping",))
    cands, q = candidates([news, social, shop], _row(), "phone", (), False)
    assert q == "exact" and {s.sid for s, _ in cands} == {"n", "s"}
    w = {s.sid: w for s, w in cands}
    assert w["n"] == pytest.approx(w["s"])                 # both 0.4 in the plan, same duration


def test_fallbacks_are_flagged_and_strict_refuses():
    shop = _snip("x", cats=("shopping",))
    cands, q = candidates([shop], _row(), "phone", (), False)
    assert q == "mix_fallback" and cands
    assert candidates([shop], _row(), "phone", (), True) == ([], "no_exact_snippet")
    laptop = _snip("l", role="laptop", cats=("news",))
    assert candidates([laptop], _row(), "phone", (), False)[1] == "role_fallback"
    assert candidates([], _row(), "phone", (), False) == ([], "no_snippet")


def test_mic_share_and_lookups_are_matched():
    muted, full = _snip("m", "voice_call", cats=("call",), mic_share="0.1"), _snip("f", "voice_call", cats=("call",))
    row = _row("voice_call", mix="", options="mic_share=0.1")
    assert [s.sid for s, _ in candidates([muted, full], row, "phone", (), False)[0]] == ["m"]
    assert [s.sid for s, _ in candidates([muted, full], _row("voice_call", mix=""), "phone", (), False)[0]] == ["f"]
    two, three = _snip("2", "sh_adjacent_lookup", cats=(), lookups="2"), _snip("3", "sh_adjacent_lookup", cats=(), lookups="3")
    assert [s.sid for s, _ in candidates([two, three], _row("sh_adjacent_lookup", mix="", lookups="3"),
                                         "phone", (), False)[0]] == ["3"]


def test_group_snippets_only_for_groups():
    group = _snip("g", "gaming_session", role="laptop", cats=("gaming",), companions=("voice_call",))
    solo = _snip("s", "gaming_session", role="laptop", cats=("gaming",))
    assert [s.sid for s, _ in candidates([group, solo], _row("gaming_session", "gaming:1"), "laptop", (), False)[0]] == ["s"]
    assert [s.sid for s, _ in candidates([group, solo], _row("gaming_session", "gaming:1"), "laptop",
                                         ("voice_call",), False)[0]] == ["g"]


def test_loops_prefer_long_snippets():
    short, long_ = _snip("short", "video_stream", "laptop", ("streaming",), 120), _snip("long", "video_stream", "laptop", ("streaming",), 3600)
    w = dict((s.sid, w) for s, w in candidates([short, long_], _row("video_stream", "streaming:1", 5400), "laptop", (), False)[0])
    assert w["long"] > 10 * w["short"]


def test_head_rules():
    assert _snip("p").head_us == S - 50_000                                         # page activity: first page
    assert _snip("v", "video_stream", dur=600).head_us == 60 * S
    assert _snip("g", "gaming_session", dur=1200).head_us == 300 * S               # 25 %
    assert _snip("c", "voice_call", dur=600).head_us == 20 * S


# -------------------- build --------------------

def _build(recorded, rows, dataset="syn_tgt_b", **kw):
    tmp, lib, _ = recorded
    plan = tmp / "plan.csv"
    write_plan(plan, rows)
    out = tmp / "out" / dataset
    summary = build(plan, lib, tmp / "devices.csv", dataset, out, log=lambda *_: None, **kw)
    man = {r["block_id"]: r for r in csv.DictReader(open(out / "manifest.csv"))}
    segs = list(csv.DictReader(open(out / "segments.csv")))
    pkts = [p for f in sorted((out / "ready").iterdir()) for p in iter_packets(f)]
    return out, summary, man, segs, pkts


def _day_rows(day=datetime(2026, 11, 2, tzinfo=TZ)):
    at = lambda h, m=0: day.replace(hour=h, minute=m)
    return [
        plan_row(at(7), 400, "tgt_a_phone", "phone_check", "20261102-wake_check-01", "news:0.5,social_passive:0.5"),
        plan_row(at(7, 30), 1800, "tgt_a_laptop", "video_stream", "20261102-stream-01", "streaming:1"),
        plan_row(at(8), 30, "tgt_a_phone", "phone_check", "20261102-check-01", "social_passive:1", pages="1"),
        plan_row(at(9), 36000, "tgt_a_phone", "away", "20261102-office-phone"),
        plan_row(at(20), 900, "tgt_a_laptop", "gaming_session", "20261102-gaming-01", "gaming:1"),
        plan_row(at(20), 900, "tgt_a_laptop", "voice_call", "20261102-gaming-01-voice",
                 companion_of="20261102-gaming-01", platform="discord"),
        plan_row(at(21), 600, "tgt_a_phone", "messaging", "20261102-msg-01", "messaging:1"),
        plan_row(at(22), 300, "tgt_a_phone", "crisis_resource_visit", "20261102-crisis-01", "crisis_help:1"),
    ]


def test_build_a_day(recorded):
    out, summary, man, segs, pkts = _build(recorded, _day_rows())
    assert man["20261102-wake_check-01"]["method"] == "chain"
    assert man["20261102-stream-01"]["method"] == "loop" and int(man["20261102-stream-01"]["copies"]) > 0
    assert man["20261102-check-01"]["method"] == "bounded"            # pages given: duration is an upper bound
    assert man["20261102-office-phone"]["method"] == "away" and man["20261102-office-phone"]["packets"] == "0"
    assert man["20261102-gaming-01"]["method"] == "loop"
    assert man["20261102-gaming-01-voice"]["method"] == "group of 20261102-gaming-01"
    assert man["20261102-msg-01"]["method"] == "bounded"
    assert man["20261102-crisis-01"]["method"] == "none" and man["20261102-crisis-01"]["match"] == "no_snippet"
    assert summary["packets"] == len(pkts) == sum(int(m["packets"] or 0) for m in man.values())
    # devices file for the ingest maps the target IPs to the synthetic dataset
    devs = list(csv.DictReader(open(out / "devices.csv")))
    assert {d["ip"] for d in devs} == {"10.42.1.21", "10.42.1.22"} and {d["dataset"] for d in devs} == {"syn_tgt_b"}
    assert json.loads((out / "synth.json").read_text())["dataset"] == "syn_tgt_b"


def test_output_is_time_ordered_on_target_devices_in_minute_files(recorded):
    out, _, _, _, pkts = _build(recorded, _day_rows())
    ts = [t for t, _, _ in pkts]
    assert ts == sorted(ts)
    for f in (out / "ready").iterdir():
        m = int(f.stem[4:]) * 1000
        assert m % (60 * S) == 0
        assert all(m <= t < m + 60 * S for t, _, _ in iter_packets(f))
    for _, _, d in pkts:
        ips = _ips(d)
        assert ips & {"10.42.1.21", "10.42.1.22"} and not ips & {"10.42.1.11", "10.42.1.12"}
        if d[23] == 6:
            assert l4_checksum_valid(d) is not False or _is_partial(d)


def _is_partial(d):
    total = int.from_bytes(d[16:18], "big")
    return int.from_bytes(d[34 + 16:34 + 18], "big") == _fold(_sum16(d[26:34]) + 6 + total - 20)


def test_packets_stay_inside_their_blocks(recorded):
    rows = _day_rows()
    _, _, man, segs, pkts = _build(recorded, rows)
    blocks = {r["block_id"]: r for r in rows}
    for s in segs:
        b = blocks[s["block_ids"].split(";")[0]]
        start, end = library.iso_to_us(b["start"]), library.iso_to_us(b["end"])
        assert int(s["t_from_us"]) >= start
        if s["part"] != "tail":
            assert int(s["t_to_us"]) <= end
    # each packet lies in a segment of its device
    by_ip = {}
    for s in segs:
        by_ip.setdefault(s["ip"], []).append((int(s["t_from_us"]), int(s["t_to_us"])))
    for t, _, d in pkts:
        ip = ({"10.42.1.21", "10.42.1.22"} & _ips(d)).pop()
        assert any(a <= t <= b for a, b in by_ip[ip])


def test_relative_timing_is_kept(recorded):
    tmp, lib, _ = recorded
    rows = [plan_row(datetime(2026, 11, 2, 7, tzinfo=TZ), 50, "tgt_a_phone", "phone_check", "x-pc-01", "news:1")]
    _, _, man, _, pkts = _build(recorded, rows)
    snip = man["x-pc-01"]["snippets"]
    src = list(iter_packets(lib / "snippets" / f"{snip}.pcap"))
    r = next(r for r in library.read_index(lib) if r["snippet_id"] == snip)
    t0 = library.iso_to_us(r["start"])
    want = [t - t0 for t, _, _ in src if t - t0 < 50 * S]
    start = library.iso_to_us(rows[0]["start"])
    assert [t - start for t, _, _ in pkts] == want


def test_tail_never_runs_into_the_next_block(recorded):
    day = datetime(2026, 11, 2, 7, tzinfo=TZ)
    rows = [plan_row(day, 50, "tgt_a_phone", "phone_check", "x-a-01", "news:1"),
            plan_row(day + timedelta(seconds=55), 50, "tgt_a_phone", "phone_check", "x-b-01", "social_passive:1")]
    _, _, _, segs, _ = _build(recorded, rows)
    second = library.iso_to_us(rows[1]["start"])
    assert all(int(s["t_to_us"]) <= second for s in segs if s["block_ids"] == "x-a-01")


def test_dst_day_uses_absolute_time(recorded):
    """25.10.2026: 02:30+02:00 comes 40 min before 02:10+01:00; both blocks land at their own instants."""
    a = datetime.fromisoformat("2026-10-25T02:30:00+02:00")
    b = datetime.fromisoformat("2026-10-25T02:10:00+01:00")
    rows = [plan_row(a, 50, "tgt_a_phone", "phone_check", "20261024-night-01", "news:1", day="2026-10-24"),
            plan_row(b, 50, "tgt_a_phone", "phone_check", "20261024-night-02", "news:1", day="2026-10-24")]
    _, _, man, segs, pkts = _build(recorded, rows)
    first = {s["block_ids"]: int(s["t_from_us"]) for s in segs if s["part"] == "main"}
    assert first["20261024-night-02"] - first["20261024-night-01"] == 40 * 60 * S
    assert man["20261024-night-02"]["emitted_start"].startswith("2026-10-25T02:10:00")


def test_same_seed_same_output_other_seed_other_choice(recorded):
    rows = _day_rows()
    _, s1, m1, _, p1 = _build(recorded, rows, "syn_tgt_b")
    _, s2, m2, _, p2 = _build(recorded, rows, "syn_tgt_c")
    assert p1 == p2 and [m["snippets"] for m in m1.values()] == [m["snippets"] for m in m2.values()]
    choices = set()
    for seed in range(8):
        _, _, m, _, _ = _build(recorded, rows, f"syn_tgt_s{chr(97 + seed)}", synth_seed=str(seed))
        choices.add(m["20261102-wake_check-01"]["snippets"])
    assert len(choices) > 1


def test_choice_of_a_block_does_not_depend_on_other_rows(recorded):
    rows = _day_rows()
    _, _, m1, _, _ = _build(recorded, rows, "syn_tgt_b")
    _, _, m2, _, _ = _build(recorded, [r for r in rows if r["block_id"] != "20261102-stream-01"], "syn_tgt_c")
    assert m1["20261102-wake_check-01"]["snippets"] == m2["20261102-wake_check-01"]["snippets"]


def test_overlay_when_no_group_snippet(recorded):
    day = datetime(2026, 11, 2, 18, tzinfo=TZ)
    rows = [plan_row(day, 600, "tgt_a_laptop", "video_stream", "x-vs-01", "streaming:1"),
            plan_row(day, 600, "tgt_a_laptop", "voice_call", "x-vs-01-voice", companion_of="x-vs-01")]
    _, _, man, _, _ = _build(recorded, rows)
    assert man["x-vs-01"]["note"] == "overlay" and man["x-vs-01-voice"]["note"] == "overlay"


def test_strict_leaves_fallback_rows_empty(recorded):
    rows = [plan_row(datetime(2026, 11, 2, 7, tzinfo=TZ), 60, "tgt_a_phone", "phone_check", "x-1", "shopping:1")]
    _, _, man, _, _ = _build(recorded, rows, "syn_tgt_b")
    assert man["x-1"]["match"] == "mix_fallback" and int(man["x-1"]["packets"]) > 0
    _, _, man, _, pkts = _build(recorded, rows, "syn_tgt_c", strict=True)
    assert man["x-1"]["method"] == "none" and pkts == []


def test_day_filter_and_refuses_non_empty_output(recorded):
    tmp, lib, _ = recorded
    rows = _day_rows() + [plan_row(datetime(2026, 11, 3, 7, tzinfo=TZ), 60, "tgt_a_phone", "phone_check",
                                   "20261103-wake_check-01", "news:1")]
    write_plan(tmp / "p.csv", rows)
    out = tmp / "o"
    s = build(tmp / "p.csv", lib, tmp / "devices.csv", "syn_tgt_b", out, days=["2026-11-03"], log=lambda *_: None)
    assert s["rows"] == 1
    with pytest.raises(ValueError, match="not empty"):
        build(tmp / "p.csv", lib, tmp / "devices.csv", "syn_tgt_b", out, log=lambda *_: None)


@pytest.mark.parametrize("name,ok", [("syn_insomnia_b", True), ("syn_insomnia_2", False), ("Syn_x", False),
                                     ("syn_bonus_a", False), ("syn_bras_a", False), ("gw_tgt_a", False),
                                     ("syn-x", False)])
def test_dataset_names(name, ok):
    live = {"tgt_a_phone": library.Device("tgt_a_phone", "phone", "", "10.42.1.21", "gw_tgt_a")}
    if ok:
        check_dataset(name, live)
    else:
        with pytest.raises(ValueError):
            check_dataset(name, live)


def test_coverage_and_cli(recorded, capsys):
    tmp, lib, _ = recorded
    write_plan(tmp / "plan.csv", _day_rows())
    rows = coverage(tmp / "plan.csv", lib, tmp / "devices.csv")
    by = {r["activity_id"]: r for r in rows}
    assert by["crisis_resource_visit"]["none"] == 1
    assert by["phone_check"]["exact"] + by["phone_check"]["fallback"] == 2
    assert cli.main(["coverage", "--plan", str(tmp / "plan.csv"), "--library", str(lib),
                     "--devices", str(tmp / "devices.csv")]) == 0
    assert "video_stream" in capsys.readouterr().out
    assert cli.main(["build", "--plan", str(tmp / "plan.csv"), "--library", str(lib), "--devices",
                     str(tmp / "devices.csv"), "--dataset", "gw_tgt_a", "--out", str(tmp / "bad")]) == 2
