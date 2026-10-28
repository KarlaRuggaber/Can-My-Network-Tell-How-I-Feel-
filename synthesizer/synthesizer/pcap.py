"""Minimal pcap reader/writer (stdlib only).

tapcap writes classic pcap: little-endian, microsecond timestamps, Ethernet (linktype 1). The reader also takes
big-endian and nanosecond files. Times are handled as integer microseconds since the epoch (UTC), so shifting a
packet never loses precision.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import BinaryIO, Iterator

LINKTYPE_ETHERNET = 1
_MAGICS = {
    b"\xd4\xc3\xb2\xa1": ("<", False), b"\xa1\xb2\xc3\xd4": (">", False),
    b"\x4d\x3c\xb2\xa1": ("<", True), b"\xa1\xb2\x3c\x4d": (">", True),
}


class PcapError(ValueError):
    pass


def iter_packets(path: str | Path) -> Iterator[tuple[int, int, bytes]]:
    """Yield (time in µs since epoch, original length, captured bytes). A truncated last record ends the file."""
    with open(path, "rb") as fh:
        head = fh.read(24)
        if len(head) < 24:
            return
        try:
            endian, nsec = _MAGICS[head[:4]]
        except KeyError:
            raise PcapError(f"{path}: not a pcap file (magic {head[:4].hex()})") from None
        linktype = struct.unpack(endian + "I", head[20:24])[0] & 0x0FFFFFFF
        if linktype != LINKTYPE_ETHERNET:
            raise PcapError(f"{path}: linktype {linktype}, expected Ethernet (1)")
        rec = struct.Struct(endian + "IIII")
        read = fh.read
        while True:
            h = read(16)
            if len(h) < 16:
                return
            sec, frac, incl, orig = rec.unpack(h)
            data = read(incl)
            if len(data) < incl:
                return
            yield sec * 1_000_000 + (frac // 1000 if nsec else frac), orig, data


class PcapWriter:
    """Writes little-endian µs pcap, Ethernet, like tapcap."""

    def __init__(self, path: str | Path, snaplen: int = 65535):
        self.path = Path(path)
        self._fh: BinaryIO = open(self.path, "wb")
        self._fh.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, snaplen, LINKTYPE_ETHERNET))
        self._rec = struct.Struct("<IIII")
        self.packets = 0
        self.bytes = 0

    def write(self, ts_us: int, orig_len: int, data: bytes) -> None:
        sec, usec = divmod(ts_us, 1_000_000)
        self._fh.write(self._rec.pack(sec, usec, len(data), orig_len))
        self._fh.write(data)
        self.packets += 1
        self.bytes += orig_len

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def capture_start_us(path: str | Path) -> int | None:
    """Start time of a tapcap file from its name, cap-<epoch_ms>.pcap; None for other names."""
    stem = Path(path).stem
    if stem.startswith("cap-") and stem[4:].isdigit():
        return int(stem[4:]) * 1000
    return None
