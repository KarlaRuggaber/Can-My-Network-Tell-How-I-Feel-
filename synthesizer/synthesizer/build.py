"""Segments -> time-ordered packets -> 60-s capture files + manifest (README §5–§7)."""

from __future__ import annotations

import csv
import hashlib
import heapq
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import __version__
from .catalog import S
from .library import Device, load_devices
from .pcap import PcapWriter, iter_packets
from .rewrite import Rewriter, port_shift
from .select import PlanRow, Segment, UnitPlan, load_plan, load_snippets, plan_all

TZ = ZoneInfo("Europe/Zurich")
FILE_US = 60 * S
DATASET_RE = re.compile(r"^[a-z][a-z0-9_]*[a-z_]$")
LATE_PACKET_US = 2 * S   # snippets are in capture order; tolerate this much disorder before stopping a segment

MANIFEST_COLUMNS = [
    "block_id", "day", "phase", "profile", "profile_block", "activity_id", "device", "planned_start", "planned_end",
    "duration_s", "method", "match", "snippets", "copies", "packets", "bytes", "emitted_start", "emitted_end",
    "companion_of", "flag", "note",
]
SEGMENT_COLUMNS = [
    "device", "ip", "t_from_us", "t_to_us", "from_local", "to_local", "block_ids", "snippet_id", "part",
    "src_from_s", "src_to_s", "copy", "packets", "bytes",
]


def check_dataset(name: str, live: dict[str, Device]) -> None:
    """Same rules as catalog §1 for dataset names, and never a live dataset (same IPs would mix in one folder)."""
    if not DATASET_RE.match(name):
        raise ValueError(f"dataset {name!r}: only [a-z0-9_], starting with a letter, not ending in a digit "
                         "(the app's group_prefix() strips trailing digits)")
    if "onu" in name or "bras" in name:
        raise ValueError(f"dataset {name!r} must not contain 'onu' or 'bras' (the app would classify it as ONU/BRAS)")
    if name in {d.dataset for d in live.values()}:
        raise ValueError(f"dataset {name!r} is a live dataset in devices.csv; use e.g. syn_<profile>_<letter>")


def local_iso(us: int) -> str:
    return datetime.fromtimestamp(us / S, tz=TZ).isoformat(timespec="microseconds")


def _seg_packets(seg: Segment, target: Device):
    sn = seg.snippet
    rw = Rewriter(sn.client_ip, target.ip, sn.client_mac or None, target.mac or None)
    ports = port_shift(seg.copy) if (seg.new_ports and seg.copy) else None
    base = sn.start_us + seg.src_from_us
    for ts, orig, data in iter_packets(sn.path):
        off = ts - sn.start_us
        if off < seg.src_from_us:
            continue
        if off >= seg.src_to_us:
            if off >= seg.src_to_us + LATE_PACKET_US:
                return
            continue
        new = rw.apply(data, ports)
        if new is not None:
            yield seg.at_us + (ts - base), orig, new


class MinuteWriter:
    """cap-<epoch_ms>.pcap per UTC minute, like tapcap; minutes without packets get no file."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.minute = None
        self.w: PcapWriter | None = None
        self.files = 0

    def write(self, ts: int, orig: int, data: bytes) -> None:
        m = ts - ts % FILE_US
        if self.minute is None or m > self.minute:
            self.close()
            self.minute = m
            self.w = PcapWriter(self.folder / f"cap-{m // 1000}.pcap")
            self.files += 1
        self.w.write(ts, orig, data)

    def close(self) -> None:
        if self.w:
            self.w.close()
            self.w = None


def emit(units: list[UnitPlan], targets: dict[str, Device], ready: Path) -> int:
    """k-way merge over all segments by time; a segment's file is opened only when the merge reaches its start."""
    segs = sorted((s for u in units for s in u.segments), key=lambda s: s.at_us)
    heap: list = []
    writer = MinuteWriter(ready)
    i = n = 0
    while heap or i < len(segs):
        while i < len(segs) and (not heap or segs[i].at_us <= heap[0][0]):
            seg = segs[i]
            it = _seg_packets(seg, targets[seg.device])
            first = next(it, None)
            if first is not None:
                heapq.heappush(heap, (first[0], i, first, it, seg))
            i += 1
        if not heap:
            continue
        ts, idx, (_, orig, data), it, seg = heapq.heappop(heap)
        writer.write(ts, orig, data)
        seg.packets += 1
        seg.bytes += orig
        n += 1
        nxt = next(it, None)
        if nxt is not None:
            heapq.heappush(heap, (nxt[0], idx, nxt, it, seg))
    writer.close()
    return writer.files


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_rows(units: list[UnitPlan]) -> list[dict]:
    rows = []
    for u in units:
        host = u.rows[0]
        for k, r in enumerate(u.rows):
            raw = r.raw
            segs = u.segments
            body = [s for s in segs if s.part == "body"]
            emitted = [s for s in segs if s.packets]
            rows.append({
                "block_id": r.block_id, "day": raw.get("day", ""), "phase": raw.get("phase", ""),
                "profile": raw.get("profile", ""), "profile_block": raw.get("profile_block", ""),
                "activity_id": r.activity, "device": r.device, "planned_start": raw["start"], "planned_end": raw["end"],
                "duration_s": f"{r.duration_us / S:.0f}",
                "method": u.method if k == 0 else f"group of {host.block_id}",
                "match": u.match, "snippets": ";".join(dict.fromkeys(s.snippet.sid for s in segs)),
                "copies": len(body),
                "packets": sum(s.packets for s in segs) if k == 0 else "",
                "bytes": sum(s.bytes for s in segs) if k == 0 else "",
                "emitted_start": local_iso(min(s.at_us for s in emitted)) if emitted and k == 0 else "",
                "emitted_end": local_iso(max(s.end_us for s in emitted)) if emitted and k == 0 else "",
                "companion_of": raw.get("companion_of", ""), "flag": raw.get("flag", ""), "note": u.note,
            })
    return sorted(rows, key=lambda r: (r["planned_start"], r["device"], r["block_id"]))


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in columns})


def build(plan_path: str | Path, library: str | Path, devices_path: str | Path, dataset: str, out: str | Path,
          days: list[str] | None = None, synth_seed: str | None = None, strict: bool = False,
          target_devices: str | Path | None = None, log=print) -> dict:
    out = Path(out)
    live = load_devices(devices_path)
    check_dataset(dataset, live)
    targets = load_devices(target_devices) if target_devices else live
    plan = load_plan(plan_path, days)
    if not plan:
        raise ValueError(f"{plan_path}: no plan rows" + (f" on {', '.join(days)}" if days else ""))
    missing = sorted({r.device for r in plan} - targets.keys())
    if missing:
        raise ValueError(f"plan devices not in the devices file: {', '.join(missing)}")
    ready = out / "ready"
    if ready.exists() and any(ready.iterdir()):
        raise ValueError(f"{ready} is not empty; use a new --out per synthetic instance")
    ready.mkdir(parents=True, exist_ok=True)

    snippets = load_snippets(library)
    roles = {name: d.role for name, d in targets.items()}
    units = plan_all(plan, snippets, roles, synth_seed, strict)
    files = emit(units, targets, ready)

    used = sorted({r.device for r in plan})
    write_csv(out / "devices.csv", ["device", "role", "mac", "ip", "dataset"],
              [{"device": d, "role": targets[d].role, "mac": targets[d].mac, "ip": targets[d].ip, "dataset": dataset}
               for d in used])
    mrows = manifest_rows(units)
    write_csv(out / "manifest.csv", MANIFEST_COLUMNS, mrows)
    srows = []
    for u in units:
        for s in u.segments:
            if s.src_to_us <= s.src_from_us:
                continue
            srows.append({"device": s.device, "ip": targets[s.device].ip, "t_from_us": s.at_us, "t_to_us": s.end_us,
                          "from_local": local_iso(s.at_us), "to_local": local_iso(s.end_us),
                          "block_ids": ";".join(s.block_ids), "snippet_id": s.snippet.sid, "part": s.part,
                          "src_from_s": f"{s.src_from_us / S:.6f}", "src_to_s": f"{s.src_to_us / S:.6f}",
                          "copy": s.copy, "packets": s.packets, "bytes": s.bytes})
    srows.sort(key=lambda r: (r["t_from_us"], r["device"]))
    write_csv(out / "segments.csv", SEGMENT_COLUMNS, srows)

    summary = {
        "synthesizer": __version__, "created": datetime.now(TZ).isoformat(timespec="seconds"),
        "plan": str(plan_path), "plan_sha256": _sha256(Path(plan_path)),
        "library": str(library), "library_index_sha256": _sha256(Path(library) / "index.csv"),
        "devices": str(devices_path), "target_devices": str(target_devices) if target_devices else None,
        "dataset": dataset, "days": days or "all", "synth_seed": synth_seed, "strict": strict,
        "rows": len(mrows), "files": files,
        "packets": sum(s.packets for u in units for s in u.segments),
        "methods": _count(r["method"] for r in mrows if not r["method"].startswith("group of")),
        "match": _count(r["match"] for r in mrows),
    }
    (out / "synth.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    log(f"{len(mrows)} plan rows -> {summary['packets']} packets in {files} file(s) under {ready}")
    log(f"methods: {summary['methods']}")
    log(f"match:   {summary['match']}")
    return summary


def _count(values) -> dict:
    out: dict[str, int] = {}
    for v in values:
        out[v] = out.get(v, 0) + 1
    return dict(sorted(out.items()))


def coverage(plan_path: str | Path, library: str | Path, devices_path: str | Path, days: list[str] | None = None,
             strict: bool = False) -> list[dict]:
    """Per activity: rows, planned hours, how they would be built (no packets written)."""
    targets = load_devices(devices_path)
    plan = load_plan(plan_path, days)
    units = plan_all(plan, load_snippets(library), {n: d.role for n, d in targets.items()}, None, strict)
    stats: dict[str, dict] = {}
    for u in units:
        for k, r in enumerate(u.rows):
            st = stats.setdefault(r.activity, {"activity_id": r.activity, "rows": 0, "planned_h": 0.0, "exact": 0,
                                               "fallback": 0, "none": 0, "copies": 0, "snippets": set()})
            st["rows"] += 1
            st["planned_h"] += r.duration_us / S / 3600
            if u.method in ("away", "idle"):
                continue
            if u.method == "none":
                st["none"] += 1
            elif u.match == "exact":
                st["exact"] += 1
            else:
                st["fallback"] += 1
            if k == 0:
                st["copies"] += sum(1 for s in u.segments if s.part == "body")
                st["snippets"].update(s.snippet.sid for s in u.segments)
    out = []
    for st in sorted(stats.values(), key=lambda s: -s["planned_h"]):
        st["planned_h"] = round(st["planned_h"], 1)
        st["snippets"] = len(st["snippets"])
        out.append(st)
    return out


__all__ = ["build", "coverage", "check_dataset", "PlanRow"]
