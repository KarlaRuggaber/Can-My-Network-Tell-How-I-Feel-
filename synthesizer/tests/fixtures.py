"""Test data without scapy: Ethernet/IPv4/TCP/UDP/DNS frames, a fake recording (captures + ground truth) and plans."""

from __future__ import annotations

import csv
import struct
from datetime import datetime, timedelta
from pathlib import Path

from synthesizer.catalog import S
from synthesizer.pcap import PcapWriter
from synthesizer.rewrite import _fold, _sum16, ip_bytes, mac_bytes

GW_IP, GW_MAC = "10.42.1.1", "7a:ed:b9:ef:be:13"
DEVICES_CSV = """# test devices
device,role,mac,ip,dataset
rec_a_phone,phone,02:00:0a:2a:01:0b,10.42.1.11,gw_rec_a
rec_a_laptop,laptop,02:00:0a:2a:01:0c,10.42.1.12,gw_rec_a
tgt_a_phone,phone,02:00:0a:2a:01:15,10.42.1.21,gw_tgt_a
tgt_a_laptop,laptop,02:00:0a:2a:01:16,10.42.1.22,gw_tgt_a
"""
REC = {"rec_a_phone": ("10.42.1.11", "02:00:0a:2a:01:0b"), "rec_a_laptop": ("10.42.1.12", "02:00:0a:2a:01:0c")}


def ipv4(src, dst, proto, payload, ident=1, frag=0):
    total = 20 + len(payload)
    h = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total, ident, frag, 64, proto, 0, ip_bytes(src), ip_bytes(dst))
    ck = ~_sum16(h) & 0xFFFF
    return h[:10] + ck.to_bytes(2, "big") + h[12:] + payload


def _l4_ck(src, dst, proto, seg, mode):
    pseudo = _fold(_sum16(ip_bytes(src) + ip_bytes(dst)) + proto + len(seg))
    if mode == "partial":
        return pseudo
    if mode == "zero":
        return 0
    return ~_fold(pseudo + _sum16(seg)) & 0xFFFF


def tcp(src, dst, sport, dport, payload=b"x" * 40, ck="valid", flags=0x18):
    seg = struct.pack("!HHIIBBHHH", sport, dport, 1000, 2000, 5 << 4, flags, 65535, 0, 0) + payload
    c = _l4_ck(src, dst, 6, seg, ck)
    return ipv4(src, dst, 6, seg[:16] + c.to_bytes(2, "big") + seg[18:])


def udp(src, dst, sport, dport, payload=b"y" * 30, ck="valid"):
    seg = struct.pack("!HHHH", sport, dport, 8 + len(payload), 0) + payload
    c = _l4_ck(src, dst, 17, seg, ck)
    if ck == "valid" and c == 0:
        c = 0xFFFF
    return ipv4(src, dst, 17, seg[:6] + c.to_bytes(2, "big") + seg[8:])


def eth(src_mac, dst_mac, ip_packet, ethertype=0x0800):
    return mac_bytes(dst_mac) + mac_bytes(src_mac) + ethertype.to_bytes(2, "big") + ip_packet


def dns_query(name, ident=0x1234):
    q = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
    return struct.pack("!HHHHHH", ident, 0x0100, 1, 0, 0, 0) + q + struct.pack("!HH", 1, 1)


def dns_answer(name, ip, ident=0x1234):
    q = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
    ans = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + ip_bytes(ip)
    return struct.pack("!HHHHHH", ident, 0x8180, 1, 1, 0, 0) + q + struct.pack("!HH", 1, 1) + ans


def client_frames(dev, t0_us, dur_s, server_ip, host, rate_hz=2.0, ck="valid", sport=40000, extra_dns=()):
    """A block: browser-start DNS at +1.0 s, page DNS + answer at +1.5 s, then TCP both ways until dur_s."""
    ip, mac = REC[dev]
    frames = []
    t = t0_us + 1 * S
    for name in ("accounts.google.com",) + tuple(extra_dns):
        frames.append((t, eth(mac, GW_MAC, udp(ip, GW_IP, 51000, 53, dns_query(name), ck=ck))))
        t += 10_000
    t = t0_us + int(1.5 * S)
    frames.append((t, eth(mac, GW_MAC, udp(ip, GW_IP, 51001, 53, dns_query(host), ck=ck))))
    frames.append((t + 5_000, eth(GW_MAC, mac, udp(GW_IP, ip, 53, 51001, dns_answer(host, server_ip)))))
    t = t0_us + 2 * S
    step = int(S / rate_hz)
    while t < t0_us + dur_s * S:
        frames.append((t, eth(mac, GW_MAC, tcp(ip, server_ip, sport, 443, ck=ck))))
        frames.append((t + 1_000, eth(GW_MAC, mac, tcp(server_ip, ip, 443, sport))))
        t += step
    return frames


def write_captures(folder: Path, frames: list[tuple[int, bytes]]) -> None:
    """tapcap-like: one file per 60 s (only minutes with packets), named cap-<epoch_ms>.pcap."""
    folder.mkdir(parents=True, exist_ok=True)
    by_min: dict[int, list] = {}
    for ts, f in sorted(frames, key=lambda x: x[0]):
        by_min.setdefault(ts - ts % (60 * S) + 387_000, []).append((ts, f))
    for m, fs in by_min.items():
        with PcapWriter(folder / f"cap-{m // 1000}.pcap") as w:
            for ts, f in fs:
                w.write(ts, len(f), f)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def make_recording(tmp: Path, base: datetime) -> dict:
    """Ground truth + captures of a small recorded session (times relative to `base`, an aware datetime)."""
    us = lambda dt: round(dt.timestamp() * S)
    gt = []
    frames = []

    def block(dev, act, start_s, dur_s, domains, block_id, status="ok", **kw):
        st = base + timedelta(seconds=start_s)
        en = st + timedelta(seconds=dur_s)
        gt.append({"start": iso(st), "end": iso(en), "device": dev, "activity_id": act, "domains": domains,
                   "profile": "test", "seed": "1", "block_id": block_id, "status": status})
        if status == "ok" and kw.get("server"):
            frames.extend(client_frames(dev, us(st), dur_s, kw["server"], domains.split(";")[0] or "x.test",
                                        rate_hz=kw.get("rate", 2.0), ck=kw.get("ck", "valid"),
                                        sport=kw.get("sport", 40000)))

    block("rec_a_phone", "phone_check", 0, 60, "www.20min.ch", "b-pc1", server="203.0.113.5", ck="partial")
    block("rec_a_phone", "phone_check", 100, 90, "www.tiktok.com", "b-pc2", server="203.0.113.6")
    block("rec_a_phone", "social_passive", 200, 180, "www.reddit.com", "b-sp1", server="203.0.113.7")
    block("rec_a_laptop", "video_stream", 0, 300, "www.youtube.com", "b-vs1", server="203.0.113.8", rate=5)
    block("rec_a_laptop", "gaming_session", 400, 240, "store.steampowered.com;peer.sim", "b-g1",
          server="10.43.0.13", sport=41000)
    block("rec_a_laptop", "voice_call", 400, 240, "peer.sim", "b-g1-voice", server="10.43.0.13", sport=42000)
    block("rec_a_phone", "messaging", 500, 120, "app.slack.com", "b-msg1", server="203.0.113.9")
    block("rec_a_phone", "video_stream", 700, 60, "www.youtube.com", "b-err", status="error")
    block("rec_a_phone", "idle_connected", 800, 60, "", "b-idle")
    # a stray packet of another host, an ARP frame and an IPv6 frame: never in a snippet
    frames.append((us(base) + 3 * S, eth("02:00:0a:2a:01:99", GW_MAC, tcp("10.42.1.99", "203.0.113.5", 1, 2))))
    frames.append((us(base) + 4 * S, eth(REC["rec_a_phone"][1], "ff:ff:ff:ff:ff:ff", b"\x00" * 28, 0x0806)))
    frames.append((us(base) + 5 * S, eth(REC["rec_a_phone"][1], GW_MAC, b"\x60" + b"\x00" * 39, 0x86DD)))
    write_captures(tmp / "ready", frames)
    with open(tmp / "ground_truth.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(gt[0]))
        w.writeheader()
        w.writerows(gt)
    (tmp / "devices.csv").write_text(DEVICES_CSV)
    return {"gt": gt, "frames": frames}


PLAN_COLUMNS = ["start", "end", "device", "activity_id", "domains", "profile", "seed", "block_id", "mix", "duration",
                "pages", "dwell", "lookups", "platform", "options", "day", "phase", "dataset", "profile_block",
                "companion_of", "flag"]


def plan_row(start: datetime, dur_s: int, device: str, activity: str, block_id: str, mix: str = "", **kw) -> dict:
    end = start + timedelta(seconds=dur_s)
    r = {c: "" for c in PLAN_COLUMNS}
    r.update(start=iso(start), end=iso(end), device=device, activity_id=activity, block_id=block_id, mix=mix,
             duration=str(dur_s), profile="test", seed="5", day=start.date().isoformat(), phase="profile",
             dataset="gw_tgt_a", profile_block=block_id.split("-")[1] if "-" in block_id else block_id)
    r.update(kw)
    return r


def write_plan(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PLAN_COLUMNS)
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: r["start"]))
