"""Shared PCAP -> 5-minute Parquet ETL.

Used by the upload page (pages/03_User_and_Network_Settings.py) and by the live
ingest service (ingest/tapingest.py), so both paths produce identical rows.
"""

from __future__ import annotations

import logging as _logging
import os
import re
from datetime import datetime

os.environ.setdefault("SCAPY_USE_LIBPCAP", "no")
_logging.getLogger("scapy.runtime").setLevel(_logging.ERROR)

import pandas as pd
from scapy.all import IP, TCP, UDP, DNS, DNSRR, PcapReader
from scapy.utils import PcapNgReader

PARTITION_MINUTES = 5
PARTITION_RE = re.compile(r"__(\d{8})_(\d{4})\.parquet$")
# Column added by the ingest service; lets a re-run replace rows of the same capture file.
CAPTURE_FILE_COL = "Capture File"


def sanitize_name(name: str) -> str:
    base = os.path.splitext(os.path.basename(name))[0]
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base


def floor_to_interval(ts: datetime, minutes: int = PARTITION_MINUTES) -> datetime:
    return ts.replace(second=0, microsecond=0, minute=(ts.minute // minutes) * minutes)


def partition_filename(base_name: str, key_dt: datetime) -> str:
    return f"{base_name}__{key_dt.strftime('%Y%m%d_%H%M')}.parquet"


def partition_file_to_start_dt(path: str):
    m = PARTITION_RE.search(os.path.basename(path))
    if not m:
        return None
    datestr, timestr = m.groups()
    return datetime.strptime(datestr + timestr, "%Y%m%d%H%M")


def iter_packets_any(pcap_path: str):
    ext = os.path.splitext(pcap_path)[1].lower()
    reader_cls = PcapNgReader if ext == ".pcapng" else PcapReader
    with reader_cls(pcap_path) as reader:
        for pkt in reader: yield pkt


def parse_packet_row(pkt):
    if not (IP in pkt): return None
    try:
        ts = datetime.fromtimestamp(float(pkt.time))
        ip = pkt[IP]
        proto = "TCP" if TCP in pkt else ("UDP" if UDP in pkt else "OTHER")
        sport = pkt[TCP].sport if TCP in pkt else (pkt[UDP].sport if UDP in pkt else None)
        dport = pkt[TCP].dport if TCP in pkt else (pkt[UDP].dport if UDP in pkt else None)
        tcp_flags = (pkt[TCP].flags if TCP in pkt else None)
        length = len(pkt)
        row = {"Timestamp": ts,"Date": ts.date(),"Hour": ts.hour,
               "Protocol": proto,"Source IP": ip.src,"Destination IP": ip.dst,
               "Source Port": sport,"Destination Port": dport,"TCP Flags": str(tcp_flags) if tcp_flags is not None else None,
               "Length": length}
        if pkt.haslayer(DNS):
            dns = pkt[DNS]; row["IsDNS"] = True
            if dns.qr == 0 and dns.qd is not None:
                try: row["DNS_QNAME"] = dns.qd.qname.decode(errors="ignore").rstrip(".")
                except Exception: row["DNS_QNAME"] = str(dns.qd.qname)
                row["DNS_QTYPE"] = dns.qd.qtype
            if dns.ancount and dns.an is not None:
                ans_ips, ans_names = [], []
                for i in range(int(dns.ancount)):
                    rr = dns.an[i] if isinstance(dns.an[i], DNSRR) else None
                    if isinstance(rr, DNSRR):
                        rrname = rr.rrname.decode(errors="ignore").rstrip(".") if isinstance(rr.rrname, (bytes, bytearray)) else str(rr.rrname)
                        ans_names.append(rrname)
                        try: ans_ips.append(str(rr.rdata))
                        except Exception: pass
                if ans_ips: row["DNS_ANS_IPS"] = ",".join(ans_ips)
                if ans_names: row["DNS_ANS_NAME"] = ans_names[0]
        else:
            row["IsDNS"] = False
        return row
    except Exception:
        return None


def write_parquet_atomic(df: pd.DataFrame, fpath: str, compression: str = "snappy") -> None:
    """Write next to the target and rename, so readers never see a half-written file.
    The temp name does not end in .parquet, so the app never lists it."""
    tmp = f"{fpath}.{os.getpid()}.tmp"
    try:
        df.to_parquet(tmp, index=False, engine="pyarrow", compression=compression)
        os.replace(tmp, fpath)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def merge_partition(dataset_dir: str, base_name: str, key_dt: datetime, rows: list[dict],
                    replace_capture_files: set[str]) -> tuple[str, int]:
    """Add rows to a 5-minute partition, keeping rows from other capture files.

    A window usually spans several 60-s capture files, so partitions are merged
    instead of overwritten. Existing rows whose CAPTURE_FILE_COL is in
    replace_capture_files are dropped first, which makes re-processing a file
    idempotent (e.g. after a crash between writing and recording it as done).
    """
    fpath = os.path.join(dataset_dir, partition_filename(base_name, key_dt))
    new = pd.DataFrame(rows)
    if os.path.exists(fpath):
        old = pd.read_parquet(fpath)
        if CAPTURE_FILE_COL in old.columns and replace_capture_files:
            old = old[~old[CAPTURE_FILE_COL].isin(replace_capture_files)]
        frames = [f for f in (old, new) if not f.empty]
        new = pd.concat(frames, ignore_index=True) if frames else new
    if "Timestamp" in new.columns:
        new = new.sort_values("Timestamp", kind="stable", ignore_index=True)
    write_parquet_atomic(new, fpath)
    return fpath, len(new)
