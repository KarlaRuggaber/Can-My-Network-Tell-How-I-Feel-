"""Move a recorded device's packets to another device: client IPv4 + MAC, optionally client ports.

Only the client side changes. The gateway (DNS on 10.42.1.1), the peer (10.43.0.x) and all servers keep their
addresses, so DNS answers stay valid for the flows that use them and no DNS payload is touched.

Checksums. br-sim records many container packets with offloaded checksums: the TCP/UDP field then holds only the
folded pseudo-header sum (CHECKSUM_PARTIAL), and inbound GRO packets can carry stale values. A full recompute would
change what was recorded, so each packet keeps its checksum *state*:
  - valid checksum -> still valid (RFC 1624 incremental update)
  - partial (field == pseudo-header sum) -> the pseudo-header sum of the new addresses
  - anything else -> the same offset from the correct value (incremental update)
The IPv4 header checksum is updated incrementally, which keeps it valid if it was.
"""

from __future__ import annotations

import ipaddress
from array import array
from typing import Callable

ETH_IPV4 = b"\x08\x00"
TCP, UDP = 6, 17
CSUM_OFFSET = {TCP: 16, UDP: 6}


def ip_bytes(ip: str) -> bytes:
    return ipaddress.IPv4Address(ip).packed


def mac_bytes(mac: str) -> bytes:
    parts = mac.split(":")
    if len(parts) != 6:
        raise ValueError(f"invalid MAC {mac!r}")
    return bytes(int(p, 16) for p in parts)


def _fold(s: int) -> int:
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return s


def _sum16(data: bytes) -> int:
    """One's complement sum of 16-bit big-endian words (not complemented)."""
    if len(data) % 2:
        data += b"\x00"
    a = array("H", data)
    if array("H", b"\x01\x00")[0] == 1:  # little-endian host: swap to network order
        a.byteswap()
    return _fold(sum(a))


def csum_update(csum: int, old: bytes, new: bytes) -> int:
    """RFC 1624 eqn. 3: HC' = ~(~HC + ~m + m') for a complemented checksum field."""
    s = (~csum & 0xFFFF) + (~_sum16(old) & 0xFFFF) + _sum16(new)
    return ~_fold(s) & 0xFFFF


def port_shift(k: int) -> Callable[[int], int]:
    """Bijection on 1024..65535 for copy k (k = 0: identity). Ports below 1024 never change."""
    if k == 0:
        return lambda p: p
    off = (k * 4099) % 64512
    return lambda p: p if p < 1024 else 1024 + (p - 1024 + off) % 64512


class Rewriter:
    def __init__(self, old_ip: str, new_ip: str, old_mac: str | None, new_mac: str | None):
        self.old_ip, self.new_ip = ip_bytes(old_ip), ip_bytes(new_ip)
        self.old_mac = mac_bytes(old_mac) if old_mac else None
        self.new_mac = mac_bytes(new_mac) if new_mac else None

    def apply(self, data: bytes, ports: Callable[[int], int] | None = None) -> bytes | None:
        """Rewritten frame, or None if it is not an IPv4 packet of the old client (ARP, IPv6, other hosts)."""
        if len(data) < 34 or data[12:14] != ETH_IPV4:
            return None
        ihl = (data[14] & 0x0F) * 4
        src, dst = data[26:30], data[30:34]
        if src == self.old_ip:
            out_dir = True
        elif dst == self.old_ip:
            out_dir = False
        else:
            return None
        b = bytearray(data)
        if self.new_mac is not None:
            if self.old_mac is None:  # client side by direction: source MAC outbound, destination MAC inbound
                pos = 6 if out_dir else 0
                b[pos:pos + 6] = self.new_mac
            else:
                for pos in (0, 6):
                    if b[pos:pos + 6] == self.old_mac:
                        b[pos:pos + 6] = self.new_mac
        addr_pos = 26 if out_dir else 30
        b[addr_pos:addr_pos + 4] = self.new_ip
        ip_ck = int.from_bytes(b[24:26], "big")
        b[24:26] = csum_update(ip_ck, self.old_ip, self.new_ip).to_bytes(2, "big")

        proto = b[23]
        frag_off = int.from_bytes(b[20:22], "big") & 0x1FFF
        l4 = 14 + ihl
        if proto not in CSUM_OFFSET or frag_off != 0 or len(b) < l4 + CSUM_OFFSET[proto] + 2:
            return bytes(b)
        port_pos = l4 if out_dir else l4 + 2
        old_port = bytes(b[port_pos:port_pos + 2])
        new_port = old_port
        if ports is not None:
            new_port = ports(int.from_bytes(old_port, "big")).to_bytes(2, "big")
            b[port_pos:port_pos + 2] = new_port
        ck_pos = l4 + CSUM_OFFSET[proto]
        ck = int.from_bytes(b[ck_pos:ck_pos + 2], "big")
        if proto == UDP and ck == 0:
            return bytes(b)  # no UDP checksum
        new_ck = self._l4_checksum(data, b, ihl, proto, ck, old_port, new_port, out_dir)
        if proto == UDP and new_ck == 0:
            new_ck = 0xFFFF
        b[ck_pos:ck_pos + 2] = new_ck.to_bytes(2, "big")
        return bytes(b)

    def _l4_checksum(self, old: bytes, new: bytearray, ihl: int, proto: int, ck: int,
                     old_port: bytes, new_port: bytes, out_dir: bool) -> int:
        total = int.from_bytes(old[16:18], "big")
        l4_len = total - ihl
        if l4_checksum_valid(old):
            return csum_update(ck, self.old_ip + old_port, self.new_ip + new_port)
        old_pseudo = _fold(_sum16(old[26:34]) + proto + l4_len)
        if ck == old_pseudo:  # CHECKSUM_PARTIAL: only the pseudo-header sum, ports are not in it
            return _fold(_sum16(bytes(new[26:34])) + proto + l4_len)
        return csum_update(ck, self.old_ip + old_port, self.new_ip + new_port)


def l4_checksum_valid(frame: bytes) -> bool | None:
    """True/False for a complete TCP/UDP-in-IPv4 frame, None if it cannot be checked (tests, diagnostics)."""
    if len(frame) < 34 or frame[12:14] != ETH_IPV4:
        return None
    ihl = (frame[14] & 0x0F) * 4
    proto = frame[23]
    total = int.from_bytes(frame[16:18], "big")
    if proto not in CSUM_OFFSET or len(frame) < 14 + total or int.from_bytes(frame[20:22], "big") & 0x1FFF:
        return None
    seg = frame[14 + ihl:14 + total]
    if proto == UDP and seg[6:8] == b"\x00\x00":
        return True
    s = _fold(_sum16(frame[26:34]) + proto + len(seg) + _sum16(seg))
    return s == 0xFFFF


def ip_header_valid(frame: bytes) -> bool:
    ihl = (frame[14] & 0x0F) * 4
    return _sum16(frame[14:14 + ihl]) == 0xFFFF
