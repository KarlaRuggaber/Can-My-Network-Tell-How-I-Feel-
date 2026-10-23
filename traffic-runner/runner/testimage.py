"""Generated test images for social_post: PNG files of random pixels, so the upload has the
requested size (random data does not compress) and the content is obviously not a photo."""

from __future__ import annotations

import random
import struct
import zlib
from pathlib import Path

WIDTH = 1000


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def make_png(path: Path, size_bytes: int, seed) -> Path:
    """Write a PNG of about `size_bytes` (RGB noise, WIDTH px wide), deterministic per seed."""
    rng = random.Random(seed)
    height = max(1, size_bytes // (WIDTH * 3))
    raw = b"".join(b"\x00" + rng.randbytes(WIDTH * 3) for _ in range(height))  # filter byte 0 per row
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, height, 8, 2, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(raw, 1))
           + _chunk(b"IEND", b""))
    path = Path(path)
    path.write_bytes(png)
    return path
