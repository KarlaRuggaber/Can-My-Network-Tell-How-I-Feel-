"""OS and browser background traffic of one simulated device (since 26.10).

Runs as the container's main process (`python -m runner background`, docker-compose.yml)
next to the activities started with `docker compose exec`. The sources and their rates are
in config/background.yaml. Only the standard library: no browser, a few KB per request.

The container must stay up whatever happens here: a crash would make Docker restart the
container and kill a running block. So every request catches its own errors, and if the
loop itself fails, the process logs it and sleeps until the container is stopped.
"""

from __future__ import annotations

import heapq
import json
import logging
import os
import random
import signal
import socket
import ssl
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from . import config, gtlog

log = logging.getLogger("runner.background")

REQUEST_TIMEOUT = 15   # seconds per request
READ_LIMIT = 64 * 1024  # bytes read from a response body
KINDS = ("get", "tls", "ntp")
LOG_NAME = "background-{device}.jsonl"


@dataclass(frozen=True)
class Source:
    name: str
    kind: str
    every: float  # mean interval, seconds
    url: str = ""
    host: str = ""
    port: int = 0


@dataclass(frozen=True)
class Profile:
    sources: tuple[Source, ...]
    night_factor: float
    night: tuple[int, int]  # local hours [start, end)

    def factor(self, hour: int) -> float:
        start, end = self.night
        at_night = start <= hour < end if start <= end else (hour >= start or hour < end)
        return self.night_factor if at_night else 1.0

    def per_hour(self, hour: int) -> float:
        """Expected requests per hour at this local hour."""
        return sum(3600.0 / (s.every * self.factor(hour)) for s in self.sources)


def load_profile(role: str, path: Path | None = None) -> Profile:
    path = Path(path or config.CONFIG_DIR / "background.yaml")
    data = config._load_yaml(path)
    roles = data.get("roles") or {}
    if role not in roles:
        raise config.ConfigError(f"{path}: no background sources for role '{role}'")
    r = roles[role] or {}
    night = data.get("night") or {}
    try:
        night_hours = (int(night.get("start", 0)), int(night.get("end", 6)))
        night_factor = float(r.get("night_factor", 1))
    except (TypeError, ValueError) as e:
        raise config.ConfigError(f"{path}: bad night settings: {e}") from None
    if not all(0 <= h <= 23 for h in night_hours) or night_factor <= 0:
        raise config.ConfigError(f"{path}: night hours must be 0-23 and night_factor > 0")
    sources, errors = [], []
    for i, s in enumerate(r.get("sources") or []):
        where = f"{role}.sources[{i}]"
        kind = s.get("kind")
        if kind not in KINDS:
            errors.append(f"{where}: kind must be one of {', '.join(KINDS)}")
            continue
        try:
            every = _seconds(str(s.get("every", "")))
        except ValueError:
            errors.append(f"{where}: bad every {s.get('every')!r} (use e.g. 90s, 15m, 2h)")
            continue
        url, host, port = str(s.get("url") or ""), str(s.get("host") or ""), int(s.get("port") or 0)
        if kind == "get" and not url.startswith(("http://", "https://")):
            errors.append(f"{where}: get needs an http(s) url")
        elif kind == "tls" and not (host and port):
            errors.append(f"{where}: tls needs host and port")
        elif kind == "ntp" and not host:
            errors.append(f"{where}: ntp needs a host")
        else:
            sources.append(Source(str(s.get("name") or f"{role}_{i}"), kind, every, url, host, port))
    if errors:
        raise config.ConfigError(f"{path}:\n  " + "\n  ".join(errors))
    if not sources:
        raise config.ConfigError(f"{path}: role '{role}' has no sources")
    return Profile(tuple(sources), night_factor, night_hours)


def _seconds(text: str) -> float:
    text = text.strip()
    unit = {"s": 1, "m": 60, "h": 3600}.get(text[-1:], None)
    value = float(text[:-1] if unit else text) * (unit or 1)
    if value < 10:
        raise ValueError(text)
    return value


def schedule(profile: Profile, rng: random.Random, start: float,
             hour_of: Callable[[float], int]) -> Iterator[tuple[float, Source]]:
    """Endless (time, source) events in time order. Each source is a Poisson process whose
    mean interval is stretched at night (`night_factor`). Thinning keeps the hourly rates
    exact across the night boundary: candidates come at the fastest rate and are kept with
    probability fastest/current."""
    fastest = min(1.0, profile.night_factor)

    def gap(s: Source, t: float) -> float:
        start = t
        while True:
            t += rng.expovariate(1.0 / (s.every * fastest))
            if rng.random() < fastest / profile.factor(hour_of(t)):
                return t - start

    heap = [(start + gap(s, start), i, s) for i, s in enumerate(profile.sources)]
    heapq.heapify(heap)
    while True:
        t, i, s = heapq.heappop(heap)
        yield t, s
        heapq.heappush(heap, (t + gap(s, t), i, s))


def local_hour(t: float) -> int:
    return time.localtime(t).tm_hour


# --- requests ------------------------------------------------------------------------------

def perform(s: Source) -> dict:
    """One request; never raises. Returns what is logged."""
    t0 = time.monotonic()
    out: dict = {"source": s.name, "kind": s.kind}
    try:
        if s.kind == "get":
            out["host"] = urllib.parse.urlsplit(s.url).hostname
            req = urllib.request.Request(s.url, headers={"Cache-Control": "no-cache"})
            try:
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
                    out["status"], out["bytes"] = r.status, len(r.read(READ_LIMIT))
            except urllib.error.HTTPError as e:  # 4xx/5xx is still a normal exchange
                out["status"], out["bytes"] = e.code, len(e.read(READ_LIMIT) or b"")
        elif s.kind == "tls":
            out["host"] = s.host
            ctx = ssl.create_default_context()
            with socket.create_connection((s.host, s.port), timeout=REQUEST_TIMEOUT) as raw:
                with ctx.wrap_socket(raw, server_hostname=s.host) as tls:
                    out["status"] = tls.version()
        elif s.kind == "ntp":
            out["host"] = s.host
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
                u.settimeout(REQUEST_TIMEOUT)
                u.sendto(b"\x23" + 47 * b"\0", (s.host, 123))  # NTPv4 client request
                data, _ = u.recvfrom(512)
                out["status"] = "ok" if len(data) >= 48 and struct.unpack("!B", data[:1])[0] & 7 == 4 else "bad"
        out["ok"] = True
    except Exception as e:  # noqa: BLE001 - background traffic must never stop the loop
        out["ok"], out["error"] = False, f"{type(e).__name__}: {e}"[:200]
    out["ms"] = round((time.monotonic() - t0) * 1000)
    return out


def append_log(path: Path, row: dict) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
    except OSError as e:
        log.warning("cannot write %s: %s", path, e)


# --- main loop -----------------------------------------------------------------------------

def run(device: config.Device, profile: Profile, *, log_path: Path,
        clock: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
        do: Callable[[Source], dict] = perform, hour_of: Callable[[float], int] = local_hour,
        limit: int | None = None) -> int:
    """Send the background requests until stopped (or `limit` requests, for tests)."""
    rng = random.Random(f"{device.name}/background/{int(clock() // 86400)}")
    sent = 0
    log.info("background traffic for %s (%s): %d sources, ~%.0f requests/h by day, ~%.0f at night",
             device.name, device.role, len(profile.sources), profile.per_hour(12), profile.per_hour(profile.night[0]))
    for due, s in schedule(profile, rng, clock(), hour_of):
        while (left := due - clock()) > 0:
            sleep(min(left, 60))  # short naps keep the timing right across clock changes
        row = do(s)
        row = {"ts": gtlog.now_iso(), "device": device.name, **row}
        append_log(log_path, row)
        if not row.get("ok"):
            log.info("%s failed: %s", s.name, row.get("error"))
        sent += 1
        if limit is not None and sent >= limit:
            break
    return sent


def main() -> int:
    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    try:
        name = os.environ.get("RUNNER_DEVICE")
        devices = config.load_devices()
        if name not in devices:
            raise config.ConfigError(f"RUNNER_DEVICE={name!r} is not in devices.csv")
        device = devices[name]
        if os.environ.get("RUNNER_STRICT_IP") == "1":
            from .cli import container_source_ip
            ip = container_source_ip()
            if ip != device.ip:  # traffic would land in another device's dataset
                raise config.ConfigError(f"container IP is {ip}, devices.csv says {device.ip}")
        profile = load_profile(device.role)
        log_dir = Path(os.environ.get("RUNNER_LOG_DIR", "/logs"))
        run(device, profile, log_path=log_dir / LOG_NAME.format(device=device.name))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as e:  # noqa: BLE001 - keep the container (and its blocks) alive
        log.error("background traffic stopped: %s: %s; the container keeps running", type(e).__name__, e)
        while True:
            time.sleep(3600)
    return 0
