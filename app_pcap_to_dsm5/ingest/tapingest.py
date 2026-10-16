#!/usr/bin/env python3
"""tapingest: live PCAP -> 5-minute Parquet ingest for the gateway.

Watches one or more capture folders (tapcap's ready/ dirs), parses every new
capture file with the same parser as the app's upload page, assigns each packet
to a dataset (= one simulated or real person) via devices.csv, and merges the
rows into app/processed_parquet/<dataset>/<dataset>__YYYYMMDD_HHMM.parquet.
Background traffic that is not user behaviour (gateway services, access point,
mDNS/SSDP/NTP, broadcasts) is dropped and counted per rule (--no-filter keeps it).

Run with TZ=Europe/Zurich: like the upload page, timestamps are local time.
"""

from __future__ import annotations

import argparse
import csv
import ipaddress
import logging
import os
import re
import signal
import sqlite3
import sys
import time
from collections import defaultdict
from functools import lru_cache
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

from utils.pcap_etl import (  # noqa: E402
    CAPTURE_FILE_COL,
    floor_to_interval,
    iter_packets_any,
    merge_partition,
    parse_packet_row,
)
from scapy.layers.l2 import Ether  # noqa: E402

log = logging.getLogger("tapingest")

CAPTURE_EXTS = (".pcap", ".pcapng")
DATASET_RE = re.compile(r"^[A-Za-z0-9._-]+$")
DEVICE_COLUMNS = ["device", "role", "mac", "ip", "dataset"]


# -------------------- devices.csv --------------------

class DeviceMap:
    """IP/MAC -> dataset lookup from devices.csv, reloaded when the file changes."""

    def __init__(self, path: Path):
        self.path = path
        self.mtime = None
        self.ip_to_dataset: dict[str, str] = {}
        self.mac_to_dataset: dict[str, str] = {}

    def refresh(self) -> None:
        mtime = self.path.stat().st_mtime
        if mtime == self.mtime:
            return
        self.ip_to_dataset, self.mac_to_dataset = load_devices(self.path)
        self.mtime = mtime
        log.info("Loaded %d device(s) from %s", len(self.ip_to_dataset), self.path)

    def dataset_for(self, row: dict, src_mac: str | None = None, dst_mac: str | None = None) -> str | None:
        # Source first: a device's own requests decide; replies are matched via destination.
        # MAC only as fallback, e.g. for DHCP broadcasts sent from 0.0.0.0.
        return (self.ip_to_dataset.get(row.get("Source IP")) or self.ip_to_dataset.get(row.get("Destination IP"))
                or self.mac_to_dataset.get(src_mac) or self.mac_to_dataset.get(dst_mac))


def load_devices(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(line for line in f if line.strip() and not line.lstrip().startswith("#"))
        missing = [c for c in DEVICE_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing column(s) {missing}, expected {DEVICE_COLUMNS}")
        out: dict[str, str] = {}
        devices, macs = set(), {}
        for n, r in enumerate(reader, start=2):
            r = {k: (v or "").strip() for k, v in r.items()}
            ip, ds, dev, mac = r["ip"], r["dataset"], r["device"], r["mac"].lower()
            ipaddress.IPv4Address(ip)  # raises on invalid address
            if not DATASET_RE.match(ds):
                raise ValueError(f"{path}:{n}: dataset '{ds}' may only contain A-Z a-z 0-9 . _ -")
            for value, seen, what in ((ip, out, "ip"), (dev, devices, "device"), (mac, macs, "mac")):
                if value and value in seen:
                    raise ValueError(f"{path}:{n}: duplicate {what} '{value}'")
            out[ip] = ds
            devices.add(dev)
            if mac:
                macs[mac] = ds
        return out, macs


# -------------------- background filter --------------------

MULTICAST = ipaddress.IPv4Network("224.0.0.0/4")
CHATTER_PORTS = {5353: "mdns", 1900: "ssdp", 123: "ntp"}
DHCP_PORTS = {67, 68}


class BackgroundFilter:
    """Drops packets that are not user behaviour (rules from process/MasterThesisInc.md §3).

    rule_for() returns the name of the first matching drop rule, or None to keep the packet:
      infra_device     to/from an excluded device (access point by MAC, or --exclude-ip)
      (keep)           DHCP (UDP 67/68) of clients, needed for C5_F1 re-associations;
                       the gateway's broadcast offers/acks count as "broadcast"
      mdns/ssdp/ntp    UDP 5353 / 1900 / 123: periodic device chatter
      broadcast        broadcast or multicast destination
      gateway_service  to/from the gateway except DNS (53): SSH, UniFi controller, ping ...
      no_client        neither endpoint is a client in the LAN networks
    """

    def __init__(self, gateway_ips: list[str], lan_nets: list[str], exclude_macs: list[str], exclude_ips: list[str]):
        self.gateway_ips = set(gateway_ips)
        self.lan_nets = [ipaddress.IPv4Network(n) for n in lan_nets]
        self.exclude_macs = {m.lower() for m in exclude_macs}
        self.exclude_ips = set(exclude_ips)
        self._addr = lru_cache(maxsize=65536)(self._classify_addr)

    def _classify_addr(self, ip: str) -> tuple[bool, bool]:
        """(is_client, is_broadcast_or_multicast) for one address."""
        a = ipaddress.ip_address(ip)
        if a == ipaddress.IPv4Address("255.255.255.255") or a in MULTICAST:
            return False, True
        for net in self.lan_nets:
            if a in net:
                if a == net.broadcast_address:
                    return False, True
                return (a != net.network_address and ip not in self.gateway_ips and ip not in self.exclude_ips), False
        return False, False

    def rule_for(self, row: dict, src_mac: str | None, dst_mac: str | None) -> str | None:
        src, dst = row["Source IP"], row["Destination IP"]
        if src_mac in self.exclude_macs or dst_mac in self.exclude_macs or src in self.exclude_ips or dst in self.exclude_ips:
            return "infra_device"
        ports = {p for p in (row.get("Source Port"), row.get("Destination Port")) if p is not None}
        src_client, _ = self._addr(src)
        dst_client, dst_bcast = self._addr(dst)
        if row["Protocol"] == "UDP":
            if ports and ports <= DHCP_PORTS:
                return "broadcast" if (dst_bcast and src in self.gateway_ips) else None
            for port, rule in CHATTER_PORTS.items():
                if port in ports:
                    return rule
        if dst_bcast:
            return "broadcast"
        if src in self.gateway_ips or dst in self.gateway_ips:
            return None if 53 in ports else "gateway_service"
        if not (src_client or dst_client):
            return "no_client"
        return None


# -------------------- state --------------------

class State:
    """Which capture files are done. A file is recorded only after all its rows are written."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS processed ("
            " path TEXT PRIMARY KEY, size INTEGER, processed_at REAL,"
            " packets INTEGER, rows_mapped INTEGER, rows_unmapped INTEGER, error TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS dropped ("
            " path TEXT, rule TEXT, packets INTEGER, PRIMARY KEY (path, rule))"
        )
        self.db.commit()

    def done(self) -> set[str]:
        return {p for (p,) in self.db.execute("SELECT path FROM processed")}

    def mark(self, results: list[dict]) -> None:
        self.db.executemany(
            "INSERT OR REPLACE INTO processed VALUES (:path, :size, :processed_at, :packets, :rows_mapped, :rows_unmapped, :error)",
            results,
        )
        self.db.executemany(
            "INSERT OR REPLACE INTO dropped VALUES (?, ?, ?)",
            [(r["path"], rule, n) for r in results for rule, n in r["dropped"].items()],
        )
        self.db.commit()


# -------------------- ingest --------------------

def pending_files(watch_dirs: list[Path], done: set[str], min_age: float, since: float = 0.0) -> list[Path]:
    now = time.time()
    found = []
    for d in watch_dirs:
        try:
            entries = list(os.scandir(d))
        except FileNotFoundError:
            log.warning("Watch dir %s does not exist (yet)", d)
            continue
        for e in entries:
            if not e.is_file() or not e.name.lower().endswith(CAPTURE_EXTS) or e.path in done:
                continue
            st = e.stat()
            if now - st.st_mtime < min_age:
                continue  # may still be written
            if st.st_mtime < since:
                continue  # older than --since
            found.append((st.st_mtime, e.path))
    return [Path(p) for _, p in sorted(found)]


def process_batch(files: list[Path], devices: DeviceMap, out_dir: Path, unmapped: str | None,
                  max_rows: int, bg_filter: BackgroundFilter | None = None) -> list[dict]:
    """Parse files until max_rows is reached, merge their rows into partitions, and
    return per-file results for the state db (only for the files actually consumed)."""
    buckets: dict[tuple[str, object], list[dict]] = defaultdict(list)
    seen_ips: set[str] = set()
    results = []
    n_rows = 0
    for f in files:
        if results and n_rows >= max_rows:
            break
        res = {"path": str(f), "size": f.stat().st_size, "processed_at": None,
               "packets": 0, "rows_mapped": 0, "rows_unmapped": 0, "error": None,
               "dropped": defaultdict(int)}
        try:
            for pkt in iter_packets_any(str(f)):
                res["packets"] += 1
                row = parse_packet_row(pkt)
                if row is None:
                    continue
                src_mac = dst_mac = None
                if Ether in pkt:
                    src_mac, dst_mac = pkt[Ether].src.lower(), pkt[Ether].dst.lower()
                if bg_filter is not None:
                    rule = bg_filter.rule_for(row, src_mac, dst_mac)
                    if rule is not None:
                        res["dropped"][rule] += 1
                        continue
                ds = devices.dataset_for(row, src_mac, dst_mac)
                if ds is None:
                    res["rows_unmapped"] += 1
                    if unmapped is None:
                        continue
                    ds = unmapped
                else:
                    res["rows_mapped"] += 1
                row[CAPTURE_FILE_COL] = f.name
                seen_ips.update(ip for ip in (row.get("Source IP"), row.get("Destination IP")) if ip)
                buckets[(ds, floor_to_interval(row["Timestamp"]))].append(row)
                n_rows += 1
        except Exception as e:  # truncated/corrupt capture: keep what was read, don't retry forever
            res["error"] = f"{type(e).__name__}: {e}"
            log.warning("Error reading %s after %d packets: %s", f.name, res["packets"], res["error"])
        results.append(res)

    names = {Path(r["path"]).name for r in results}
    for (ds, key), rows in sorted(buckets.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        dataset_dir = out_dir / ds
        dataset_dir.mkdir(parents=True, exist_ok=True)
        fpath, total = merge_partition(str(dataset_dir), ds, key, rows, names)
        log.debug("%s: +%d rows (now %d)", os.path.basename(fpath), len(rows), total)

    if seen_ips:
        update_known_ips(out_dir / "known_ips.txt", seen_ips)
    now = time.time()
    for r in results:
        r["processed_at"] = now
    return results


def update_known_ips(path: Path, ips: set[str]) -> None:
    """Same catalog the upload page maintains (processed_parquet/known_ips.txt)."""
    try:
        known = {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}
    except FileNotFoundError:
        known = set()
    if ips <= known:
        return
    tmp = path.with_suffix(".txt.tmp")
    tmp.write_text("".join(f"{ip}\n" for ip in sorted(known | ips)), encoding="utf-8")
    os.replace(tmp, path)


# -------------------- main loop --------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--watch", action="append", required=True, type=Path,
                   help="Folder with finished capture files (repeatable), e.g. /var/lib/tapcap/ready")
    p.add_argument("--devices", required=True, type=Path, help="devices.csv (device,role,mac,ip,dataset)")
    p.add_argument("--out", type=Path, default=APP_DIR / "processed_parquet",
                   help="The app's processed_parquet folder (default: %(default)s)")
    p.add_argument("--state", type=Path, default=Path("/var/lib/tapingest/state.sqlite"),
                   help="SQLite file remembering processed captures (default: %(default)s)")
    p.add_argument("--unmapped", default="gw_unassigned",
                   help="Dataset for packets of devices not in devices.csv, or 'drop' (default: %(default)s)")
    p.add_argument("--poll", type=float, default=10, help="Seconds between folder scans (default: %(default)s)")
    p.add_argument("--batch", type=int, default=30, help="Max capture files per batch (default: %(default)s)")
    p.add_argument("--max-rows", type=int, default=300_000,
                   help="Close a batch once this many rows are buffered; bounds memory (default: %(default)s)")
    p.add_argument("--min-age", type=float, default=5,
                   help="Ignore files modified less than this many seconds ago (default: %(default)s)")
    p.add_argument("--since", type=datetime.fromisoformat, default=None,
                   help="Ignore capture files last modified before this local time, e.g. 2026-10-16T18:00")
    p.add_argument("--no-filter", action="store_true",
                   help="Keep background traffic (gateway services, AP, mDNS/SSDP/NTP, broadcasts)")
    p.add_argument("--gateway-ip", action="append", default=None,
                   help="Gateway address(es); only DNS to/from them is kept (default: 10.42.0.1, 10.42.1.1)")
    p.add_argument("--lan-net", action="append", default=None,
                   help="Client networks (default: 10.42.0.0/24, 10.42.1.0/24)")
    p.add_argument("--exclude-mac", action="append", default=[],
                   help="Infrastructure device to drop entirely, e.g. the access point (repeatable)")
    p.add_argument("--exclude-ip", action="append", default=[],
                   help="Infrastructure address to drop entirely (repeatable)")
    p.add_argument("--once", action="store_true", help="Process everything pending, then exit (backfill/tests)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    if args.unmapped != "drop" and not DATASET_RE.match(args.unmapped):
        p.error("--unmapped must be 'drop' or a valid dataset name")
    args.gateway_ip = args.gateway_ip or ["10.42.0.1", "10.42.1.1"]
    args.lan_net = args.lan_net or ["10.42.0.0/24", "10.42.1.0/24"]
    try:
        for ip in args.gateway_ip + args.exclude_ip:
            ipaddress.IPv4Address(ip)
        for net in args.lan_net:
            ipaddress.IPv4Network(net)
    except ValueError as e:
        p.error(str(e))
    for mac in args.exclude_mac:
        if not re.fullmatch(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", mac):
            p.error(f"invalid --exclude-mac {mac!r}")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if os.environ.get("TZ") != "Europe/Zurich":
        log.warning("TZ is %r; profiles and the app expect Europe/Zurich local time", os.environ.get("TZ"))

    unmapped = None if args.unmapped == "drop" else args.unmapped
    since = args.since.timestamp() if args.since else 0.0
    bg_filter = None if args.no_filter else BackgroundFilter(args.gateway_ip, args.lan_net, args.exclude_mac, args.exclude_ip)
    devices = DeviceMap(args.devices)
    state = State(args.state)
    args.out.mkdir(parents=True, exist_ok=True)

    stop = False
    def _stop(signum, _frame):
        nonlocal stop
        log.info("Signal %d received, stopping after current batch", signum)
        stop = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    log.info("Watching %s -> %s (unmapped: %s)", ", ".join(map(str, args.watch)), args.out, args.unmapped)
    if args.since:
        log.info("Ignoring capture files modified before %s", args.since.isoformat())
    if bg_filter is None:
        log.info("Background filter disabled (--no-filter)")
    else:
        log.info("Background filter on: gateway %s, LAN %s, excluded MACs %s, excluded IPs %s",
                 ",".join(args.gateway_ip), ",".join(args.lan_net), ",".join(args.exclude_mac) or "-",
                 ",".join(args.exclude_ip) or "-")
    while not stop:
        devices.refresh()
        files = pending_files(args.watch, state.done(), 0 if args.once else args.min_age, since)
        if not files:
            if args.once:
                break
            time.sleep(args.poll)
            continue
        t0 = time.monotonic()
        results = process_batch(files[: args.batch], devices, args.out, unmapped, args.max_rows, bg_filter)
        state.mark(results)
        pkts = sum(r["packets"] for r in results)
        dropped = sum(sum(r["dropped"].values()) for r in results)
        dt = time.monotonic() - t0
        log.info("Ingested %d file(s), %d packets (%d dropped as background) in %.1fs (%.0f pkt/s), %d file(s) still pending",
                 len(results), pkts, dropped, dt, pkts / dt if dt else 0, len(files) - len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
