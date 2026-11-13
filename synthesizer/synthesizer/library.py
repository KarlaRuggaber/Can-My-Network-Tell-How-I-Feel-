"""Snippet library: recorded blocks cut out of the br-sim captures by the runner's ground truth (README §2).

    library/index.csv                  one row per snippet (INDEX_COLUMNS)
    library/snippets/<snippet_id>.pcap the device's packets of that block, original addresses and times

A snippet is one ground-truth row with status ok on one device; a host block and its companions (`…-voice`,
`…-bg`, same device, same IP) are one group snippet, because their packets cannot be told apart.
"""

from __future__ import annotations

import bisect
import csv
import ipaddress
import re
import shlex
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import catalog
from .catalog import S
from .pcap import PcapWriter, capture_start_us, iter_packets

INDEX_COLUMNS = [
    "snippet_id", "activity_id", "companions", "role", "device", "client_ip", "client_mac",
    "start", "end", "duration_s", "tail_s", "first_page_s", "packets", "bytes", "dns_queries", "domains", "categories",
    "mix", "mic_share", "pages", "lookups", "block_ids", "profile", "seed", "captures", "flags",
]
DEVICE_COLUMNS = ["device", "role", "mac", "ip", "dataset"]
CAPTURE_SPAN_US = 65 * S       # tapcap rotates every 60 s (a new file only when packets arrive)
DEFAULT_TAIL_S = 30            # browser shutdown after the logged end (pilot: up to 16 s)
OVERLAP_TOLERANCE_US = 30 * S  # back-to-back blocks may overlap by a few seconds (end is logged after the browser closed)


# -------------------- devices --------------------

@dataclass(frozen=True)
class Device:
    name: str
    role: str
    mac: str
    ip: str
    dataset: str


def load_devices(path: str | Path) -> dict[str, Device]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(line for line in f if line.strip() and not line.lstrip().startswith("#"))
        missing = [c for c in DEVICE_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing column(s) {missing}")
        out = {}
        for r in reader:
            r = {k: (v or "").strip() for k, v in r.items()}
            ipaddress.IPv4Address(r["ip"])
            out[r["device"]] = Device(r["device"], r["role"], r["mac"].lower(), r["ip"], r["dataset"])
        return out


def apply_aliases(devices: dict[str, Device], aliases: list[str]) -> dict[str, Device]:
    """`old=new`: a device renamed since the recording (student01_phone=student_a_phone) has new's IP/MAC/role."""
    out = dict(devices)
    for a in aliases:
        old, sep, new = a.partition("=")
        if not sep or new not in devices:
            raise ValueError(f"--alias {a!r}: expected OLD=NEW with NEW in devices.csv")
        d = devices[new]
        out[old] = Device(old, d.role, d.mac, d.ip, d.dataset)
    return out


# -------------------- ground truth + plan joins --------------------

def iso_to_us(text: str) -> int:
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError(f"time without UTC offset: {text!r}")
    return round(dt.timestamp() * S)


def load_ground_truth(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)]
    for r in rows:
        r["start_us"], r["end_us"] = iso_to_us(r["start"]), iso_to_us(r["end"])
    return rows


def _mic_share(text: str | None) -> str:
    if not text:
        return ""
    t = text.strip()
    v = float(t[:-1]) / 100 if t.endswith("%") else float(t)
    return f"{v:g}"


def load_block_info(plans: list[str | Path], commands: list[str | Path]) -> dict[str, dict]:
    """block_id -> {mix, mic_share, pages, lookups} from plan CSVs and runner command files (the GT has no mix)."""
    info: dict[str, dict] = {}
    for p in plans:
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                opts = catalog.parse_options(r.get("options"))
                info[r["block_id"]] = {"mix": r.get("mix", ""), "mic_share": _mic_share(opts.get("mic_share")),
                                       "pages": r.get("pages", ""), "lookups": r.get("lookups", "")}
    flags = {"--mix": "mix", "--mic-share": "mic_share", "--pages": "pages", "--lookups": "lookups"}
    for p in commands:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            cols = line.split("\t")
            args = shlex.split(cols[-1])
            d = {"mix": "", "mic_share": "", "pages": "", "lookups": ""}
            block = None
            for i, a in enumerate(args[:-1]):
                if a == "--block-id":
                    block = args[i + 1]
                elif a in flags:
                    d[flags[a]] = _mic_share(args[i + 1]) if a == "--mic-share" else args[i + 1]
            if block:
                info[block] = d
    return info


# -------------------- units (snippet candidates) --------------------

@dataclass
class Unit:
    host: dict
    companions: list[dict] = field(default_factory=list)
    window_end_us: int = 0
    flags: list[str] = field(default_factory=list)

    @property
    def start_us(self) -> int:
        return self.host["start_us"]

    @property
    def end_us(self) -> int:
        return max([self.host["end_us"]] + [c["end_us"] for c in self.companions])


def build_units(gt: list[dict], tail_s: float = DEFAULT_TAIL_S) -> list[Unit]:
    """Group companions with their host, then set each unit's window end per device:
    min(end + tail, next unit's start). Units overlapping a later one by more than the tolerance are ambiguous."""
    by_dev: dict[str, list[dict]] = {}
    for r in gt:
        by_dev.setdefault(r["device"], []).append(r)
    units: list[Unit] = []
    for dev, rows in by_dev.items():
        ids = {r["block_id"] for r in rows}
        hosts: dict[str, Unit] = {}
        comps = []
        for r in sorted(rows, key=lambda r: (r["start_us"], r["block_id"])):
            host_id = next((r["block_id"][: -len(s)] for s in catalog.COMPANION_SUFFIXES
                            if r["block_id"].endswith(s)), None)
            if host_id and host_id in ids and host_id != r["block_id"]:
                comps.append((host_id, r))
            else:
                hosts.setdefault(r["block_id"] + "@" + r["start"], Unit(r))
        for host_id, r in comps:
            cand = [u for u in hosts.values() if u.host["block_id"] == host_id
                    and abs(u.start_us - r["start_us"]) <= OVERLAP_TOLERANCE_US]
            if cand:
                cand[0].companions.append(r)
            else:
                hosts[r["block_id"] + "@" + r["start"]] = Unit(r)
        dev_units = sorted(hosts.values(), key=lambda u: u.start_us)
        for i, u in enumerate(dev_units):
            end = u.end_us + round(tail_s * S)
            if i + 1 < len(dev_units):
                nxt = dev_units[i + 1]
                if nxt.start_us < u.end_us - OVERLAP_TOLERANCE_US:
                    u.flags.append("ambiguous")
                    nxt.flags.append("ambiguous")
                end = min(end, nxt.start_us)
            u.window_end_us = max(end, u.start_us)
        units.extend(dev_units)
    return sorted(units, key=lambda u: (u.start_us, u.host["device"]))


def us_to_iso(us: int, like: str) -> str:
    """Instant as ISO-8601 with the UTC offset of `like` (an ISO time from the same file)."""
    return datetime.fromtimestamp(us / S, tz=datetime.fromisoformat(like).tzinfo).isoformat()


def snippet_id(unit: Unit) -> str:
    t = datetime.fromisoformat(unit.host["start"]).strftime("%Y%m%dT%H%M%S")
    sid = f"{t}-{unit.host['device']}-{unit.host['activity_id']}"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", sid)


# -------------------- index --------------------

def read_index(library: str | Path) -> list[dict]:
    path = Path(library) / "index.csv"
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_index(library: str | Path, rows: list[dict]) -> None:
    path = Path(library) / "index.csv"
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_COLUMNS)
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["start"], r["device"])):
            w.writerow({k: r.get(k, "") for k in INDEX_COLUMNS})
    tmp.replace(path)


# -------------------- cutting --------------------

def capture_files(dirs: list[str | Path]) -> list[tuple[int, Path]]:
    files = []
    for d in dirs:
        for p in Path(d).iterdir():
            s = capture_start_us(p)
            if s is not None and p.suffix == ".pcap":
                files.append((s, p))
    return sorted(files)


def cut(ground_truth: str | Path, capture_dirs: list[str | Path], devices: dict[str, Device], library: str | Path,
        block_info: dict[str, dict] | None = None, mixes_yaml: str | Path | None = None,
        tail_s: float = DEFAULT_TAIL_S, include_status: tuple[str, ...] = ("ok",), log=print) -> list[dict]:
    """Cut new snippets into the library and return the new index rows. Existing snippet IDs are kept as they are."""
    library = Path(library)
    (library / "snippets").mkdir(parents=True, exist_ok=True)
    block_info = block_info or {}
    host_cats = catalog.load_host_categories(mixes_yaml)
    index = {r["snippet_id"]: r for r in read_index(library)}
    files = capture_files(capture_dirs)
    units = build_units(load_ground_truth(ground_truth), tail_s)

    todo: list[tuple[Unit, dict]] = []
    skipped: dict[str, int] = {}
    for u in units:
        h = u.host
        reason = None
        if h["status"] not in include_status:
            reason = f"status {h['status']}"
        elif h["activity_id"] in catalog.NOTHING:
            reason = h["activity_id"]
        elif h["device"] not in devices:
            reason = "device not in devices.csv (use --alias)"
        elif "ambiguous" in u.flags:
            reason = "overlaps another block on the device"
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        sid = snippet_id(u)
        if sid in index:
            skipped["already in the library"] = skipped.get("already in the library", 0) + 1
            continue
        dev = devices[h["device"]]
        info = block_info.get(h["block_id"], {})
        hosts = [d for d in h["domains"].split(";") if d]
        mix = info.get("mix", "")
        flags = list(u.flags)
        row = {
            "snippet_id": sid, "activity_id": h["activity_id"],
            "companions": ";".join(sorted(c["activity_id"] for c in u.companions)),
            "role": dev.role, "device": h["device"], "client_ip": dev.ip, "client_mac": dev.mac,
            "start": h["start"], "end": us_to_iso(u.end_us, h["start"]),
            "duration_s": f"{(min(u.end_us, u.window_end_us) - u.start_us) / S:.3f}",
            "tail_s": f"{max(0, u.window_end_us - u.end_us) / S:.3f}",
            "domains": h["domains"],
            "categories": ";".join(catalog.categories_of(hosts, h["activity_id"], host_cats, catalog.parse_mix(mix))),
            "mix": mix, "mic_share": info.get("mic_share", ""), "pages": info.get("pages", ""),
            "lookups": info.get("lookups", "") or (str(len(hosts)) if h["activity_id"] == "sh_adjacent_lookup" else ""),
            "block_ids": ";".join([h["block_id"]] + [c["block_id"] for c in u.companions]),
            "profile": h["profile"], "seed": h["seed"], "flags": ";".join(flags),
            "_t0": u.start_us, "_t1": u.window_end_us,
        }
        todo.append((u, row))

    if todo:
        _extract(todo, files, library)
    new_rows = []
    for _, row in todo:
        if row["packets"] == 0:
            row["flags"] = ";".join(filter(None, [row["flags"], "empty"]))
        index[row["snippet_id"]] = {k: v for k, v in row.items() if not k.startswith("_")}
        new_rows.append(index[row["snippet_id"]])
    write_index(library, list(index.values()))
    for reason, n in sorted(skipped.items()):
        log(f"skipped {n} ground-truth block(s): {reason}")
    log(f"cut {len(new_rows)} snippet(s) into {library}")
    return new_rows


def _extract(todo: list[tuple[Unit, dict]], files: list[tuple[int, Path]], library: Path) -> None:
    """One pass over the capture files; every packet of a client IP goes to the window that contains it."""
    windows: dict[bytes, list[tuple[int, int, dict]]] = {}
    for _, row in todo:
        ip = ipaddress.IPv4Address(row["client_ip"]).packed
        windows.setdefault(ip, []).append((row["_t0"], row["_t1"], row))
        row.update(packets=0, bytes=0, dns_queries=0, first_page_s="", _captures=set(), _writer=None,
                   _page=(row["domains"].split(";")[0].lower() if row["domains"] else None))
    starts = {ip: [w[0] for w in sorted(ws, key=lambda w: w[0])] for ip, ws in windows.items()}
    for ip in windows:
        windows[ip].sort(key=lambda w: w[0])
    t_min = min(w[0] for ws in windows.values() for w in ws)
    t_max = max(w[1] for ws in windows.values() for w in ws)
    open_rows: list[dict] = []
    for i, (fstart, path) in enumerate(files):
        fend = files[i + 1][0] if i + 1 < len(files) else fstart + CAPTURE_SPAN_US
        if fend <= t_min or fstart >= t_max:
            continue
        for ts, orig, data in iter_packets(path):
            if len(data) < 34 or data[12:14] != b"\x08\x00":
                continue
            for ip, out_dir in ((data[26:30], True), (data[30:34], False)):
                ws = windows.get(ip)
                if ws is None:
                    continue
                j = bisect.bisect_right(starts[ip], ts) - 1
                if j < 0 or ts >= ws[j][1]:
                    continue
                row = ws[j][2]
                if row["_writer"] is None:
                    row["_writer"] = PcapWriter(library / "snippets" / f"{row['snippet_id']}.pcap")
                    open_rows.append(row)
                row["_writer"].write(ts, orig, data)
                row["packets"] += 1
                row["bytes"] += orig
                row["_captures"].add(path.name)
                l4 = 14 + (data[14] & 15) * 4
                if out_dir and data[23] == 17 and data[l4 + 2:l4 + 4] == b"\x00\x35":
                    row["dns_queries"] += 1
                    if row["_page"] and row["first_page_s"] == "" and dns_qname(data[l4 + 8:]) == row["_page"]:
                        row["first_page_s"] = f"{(ts - row['_t0']) / S:.3f}"
                break
        for row in [r for r in open_rows if r["_t1"] <= fend]:
            row["_writer"].close()
            open_rows.remove(row)
    for row in open_rows:
        row["_writer"].close()
    for _, row in todo:
        if row["_writer"] is None:  # no packets: still write an empty file, so every index row has one
            PcapWriter(library / "snippets" / f"{row['snippet_id']}.pcap").close()
        caps = sorted(row.pop("_captures"))
        row["captures"] = f"{caps[0]}..{caps[-1]} ({len(caps)})" if caps else ""
        row.pop("_writer")
        row.pop("_page")


def dns_qname(msg: bytes) -> str | None:
    """First question name of a DNS message (no compression in questions), lower case, or None."""
    labels, i = [], 12
    try:
        while msg[i]:
            n = msg[i]
            if n & 0xC0:
                return None
            labels.append(msg[i + 1:i + 1 + n].decode("ascii", "replace"))
            i += 1 + n
    except IndexError:
        return None
    return ".".join(labels).lower()


def snippet_path(library: str | Path, sid: str) -> Path:
    return Path(library) / "snippets" / f"{sid}.pcap"


def main_log(msg: str) -> None:
    print(msg, file=sys.stderr)
