"""Load and validate the runner configuration: devices.csv, mixes.yaml, roles.yaml."""

from __future__ import annotations

import csv
import ipaddress
import os
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_DIR = Path(os.environ.get("RUNNER_CONFIG_DIR", Path(__file__).resolve().parent.parent / "config"))

# devices.csv is the shared interface with the ingest service: do not change the columns
# without agreeing on it first.
DEVICE_COLUMNS = ["device", "role", "mac", "ip", "dataset"]
ROLES = ("phone", "laptop")
SIM_IP_FIRST = ipaddress.IPv4Address("10.42.1.10")
SIM_IP_LAST = ipaddress.IPv4Address("10.42.1.254")

_NAME_RE = re.compile(r"^[a-z0-9_]+$")
_MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")


class ConfigError(ValueError):
    """Invalid configuration file."""


class MixUnavailable(RuntimeError):
    """No site in the requested mix can be used (e.g. all need a login)."""


# --- devices.csv -------------------------------------------------------------------------

@dataclass(frozen=True)
class Device:
    name: str
    role: str
    mac: str
    ip: str
    dataset: str


def load_devices(path: Path | None = None) -> dict[str, Device]:
    """Read devices.csv and validate every row. Raises ConfigError listing all problems."""
    path = Path(path or CONFIG_DIR / "devices.csv")
    errors: list[str] = []
    devices: dict[str, Device] = {}
    seen_mac: dict[str, str] = {}
    seen_ip: dict[str, str] = {}

    # Lines starting with "#" are comments (same format as the ingest, which reads this file too).
    with open(path, newline="", encoding="utf-8") as f:
        kept = [(n, line) for n, line in enumerate(f.read().splitlines(), start=1)
                if line.strip() and not line.lstrip().startswith("#")]
    reader = csv.DictReader([line for _, line in kept])
    if reader.fieldnames != DEVICE_COLUMNS:
        raise ConfigError(f"{path}: header must be {','.join(DEVICE_COLUMNS)}, got {reader.fieldnames}")
    for (lineno, _), row in zip(kept[1:], reader):
        where = f"{path.name}:{lineno}"
        if None in row or any(v is None for v in row.values()):
            errors.append(f"{where}: expected {len(DEVICE_COLUMNS)} columns")
            continue
        if any(v != v.strip() for v in row.values()):
            errors.append(f"{where}: values must not contain surrounding whitespace")
            continue
        name, role, mac, ip, dataset = (row[c] for c in DEVICE_COLUMNS)

        if not _NAME_RE.match(name):
            errors.append(f"{where}: device '{name}' must match [a-z0-9_]+")
        elif name in devices:
            errors.append(f"{where}: duplicate device '{name}'")
        if role not in ROLES:
            errors.append(f"{where}: role '{role}' must be one of {', '.join(ROLES)}")
        errors.extend(f"{where}: {e}" for e in _mac_errors(mac))
        errors.extend(f"{where}: {e}" for e in _ip_errors(ip))
        if not _NAME_RE.match(dataset):
            errors.append(f"{where}: dataset '{dataset}' must match [a-z0-9_]+")
        else:
            errors.extend(f"{where}: {e}" for e in _dataset_errors(dataset))

        if mac in seen_mac:
            errors.append(f"{where}: MAC {mac} already used by {seen_mac[mac]}")
        if ip in seen_ip:
            errors.append(f"{where}: IP {ip} already used by {seen_ip[ip]}")
        seen_mac.setdefault(mac, name)
        seen_ip.setdefault(ip, name)
        devices.setdefault(name, Device(name, role, mac, ip, dataset))

    if not devices and not errors:
        errors.append(f"{path}: no devices defined")
    if errors:
        raise ConfigError("\n".join(errors))
    return devices


def _mac_errors(mac: str) -> list[str]:
    if not _MAC_RE.match(mac):
        return [f"MAC '{mac}' must be lower-case aa:bb:cc:dd:ee:ff"]
    first = int(mac[:2], 16)
    errors = []
    if not first & 0x02:
        errors.append(f"MAC {mac} must be locally administered (first octet like 02, 06, 0a, ...)")
    if first & 0x01:
        errors.append(f"MAC {mac} is a multicast address")
    return errors


def _dataset_errors(dataset: str) -> list[str]:
    """Naming rules of activity-catalog §1 (gw_<profile>_<letter>)."""
    errors = []
    if not dataset.startswith("gw_"):
        errors.append(f"dataset '{dataset}' must start with gw_")
    if dataset[-1].isdigit():
        errors.append(f"dataset '{dataset}' must not end with a digit: the app strips trailing digits"
                      " and would merge it with other datasets (use gw_<profile>_<letter>)")
    for word in ("onu", "bras"):
        if word in dataset:
            errors.append(f"dataset '{dataset}' must not contain '{word}': the app would treat it"
                          f" as an {word.upper()} dataset")
    return errors


def _ip_errors(ip: str) -> list[str]:
    try:
        addr = ipaddress.IPv4Address(ip)
    except ValueError:
        return [f"IP '{ip}' is not a valid IPv4 address"]
    if not SIM_IP_FIRST <= addr <= SIM_IP_LAST:
        return [f"IP {ip} must be within {SIM_IP_FIRST}-{SIM_IP_LAST}"]
    return []


# --- roles.yaml --------------------------------------------------------------------------

def load_roles(path: Path | None = None) -> dict:
    path = Path(path or CONFIG_DIR / "roles.yaml")
    data = _load_yaml(path)
    missing = [r for r in ROLES if "playwright_device" not in (data.get(r) or {})]
    if missing:
        raise ConfigError(f"{path}: no playwright_device for role(s) {', '.join(missing)}")
    return data


# --- accounts.yaml -----------------------------------------------------------------------

def load_accounts(path: Path | None = None) -> dict:
    path = Path(path or CONFIG_DIR / "accounts.yaml")
    data = _load_yaml(path)
    sub = str((data.get("reddit") or {}).get("subreddit", ""))
    if not sub or not re.match(r"^[A-Za-z0-9_]{3,21}$", sub):
        raise ConfigError(f"{path}: reddit.subreddit must be a subreddit name, got {sub!r}")
    return data


# --- mixes.yaml --------------------------------------------------------------------------

@dataclass(frozen=True)
class Site:
    category: str
    host: str
    url: str
    login: bool = False
    kind: str = "page"
    playable: bool = True
    queries: tuple[str, ...] = ()

    def resolve_url(self, rng: random.Random) -> str:
        """Start URL; draws a search query from the RNG only if the site has queries."""
        if not self.queries:
            return self.url
        from urllib.parse import quote_plus
        return self.url.replace("{query}", quote_plus(rng.choice(self.queries)))


@dataclass
class Mixes:
    categories: dict[str, list[Site]]
    video: dict = field(default_factory=dict)
    audio: dict = field(default_factory=dict)
    consent: dict = field(default_factory=dict)
    documents: dict = field(default_factory=dict)


def load_mixes(path: Path | None = None) -> Mixes:
    path = Path(path or CONFIG_DIR / "mixes.yaml")
    data = _load_yaml(path)
    categories: dict[str, list[Site]] = {}
    errors: list[str] = []
    for cat, spec in (data.get("categories") or {}).items():
        sites = []
        for i, s in enumerate((spec or {}).get("sites") or []):
            if not isinstance(s, dict) or "host" not in s or "url" not in s:
                errors.append(f"{path.name}: {cat}[{i}] needs host and url")
                continue
            if s.get("kind", "page") not in ("page", "video"):
                errors.append(f"{path.name}: {cat}[{i}] kind must be page or video")
            if "{query}" in s["url"] and not s.get("queries"):
                errors.append(f"{path.name}: {cat}[{i}] url has {{query}} but no queries")
            sites.append(Site(
                category=cat,
                host=s["host"],
                url=s["url"],
                login=bool(s.get("login", False)),
                kind=s.get("kind", "page"),
                playable=bool(s.get("playable", True)),
                queries=tuple(s.get("queries") or ()),
            ))
        if not sites:
            errors.append(f"{path.name}: category '{cat}' has no sites")
        categories[cat] = sites
    if errors:
        raise ConfigError("\n".join(errors))
    return Mixes(categories, data.get("video") or {}, data.get("audio") or {}, data.get("consent") or {},
                 data.get("documents") or {})


@dataclass(frozen=True)
class Mix:
    """Weighted choice of sites from one or more categories, e.g. news:.2,social_passive:.4."""

    weights: tuple[tuple[str, float], ...]
    sites: dict[str, tuple[Site, ...]]
    skipped: tuple[str, ...] = ()

    @property
    def categories(self) -> list[str]:
        return [c for c, _ in self.weights]

    def pick(self, rng: random.Random) -> Site:
        """Category by weight, then a site uniformly. Depends only on the RNG state."""
        cats = [c for c, _ in self.weights]
        cat = rng.choices(cats, weights=[w for _, w in self.weights])[0]
        return rng.choice(self.sites[cat])

    def all_sites(self) -> list[Site]:
        return [s for c in self.categories for s in self.sites[c]]


def parse_mix(spec: str, mixes: Mixes, kind: str | None = None) -> Mix:
    """Parse `news,social_passive` (equal weights) or `news:.2,social_passive:.4`.

    Sites that need a login (or cannot be played, for kind=video) are dropped. Categories
    left empty are dropped with their weight. Raises ConfigError for unknown categories or
    bad weights and MixUnavailable if nothing usable is left.
    """
    weights: list[tuple[str, float]] = []
    for part in (p.strip() for p in spec.split(",")):
        if not part:
            continue
        name, _, w = part.partition(":")
        name = name.strip()
        if name not in mixes.categories:
            raise ConfigError(f"unknown mix category '{name}' (known: {', '.join(mixes.categories)})")
        try:
            weight = float(w) if w else 1.0
        except ValueError:
            raise ConfigError(f"bad weight in mix part '{part}'") from None
        if weight <= 0:
            raise ConfigError(f"weight must be > 0 in mix part '{part}'")
        if name in dict(weights):
            raise ConfigError(f"category '{name}' listed twice in mix")
        weights.append((name, weight))
    if not weights:
        raise ConfigError("empty mix")

    usable: dict[str, tuple[Site, ...]] = {}
    skipped: list[str] = []
    for name, _ in weights:
        sites = tuple(
            s for s in mixes.categories[name]
            if not s.login and (kind is None or (s.kind == kind and s.playable))
        )
        if sites:
            usable[name] = sites
        else:
            skipped.append(name)
    kept = tuple((n, w) for n, w in weights if n in usable)
    if not kept:
        raise MixUnavailable(f"no usable site in mix '{spec}' (login needed or not playable)")
    return Mix(kept, usable, tuple(skipped))


def _load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return data
