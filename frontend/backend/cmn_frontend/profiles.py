"""Person profiles: who is monitored, from which traffic source, and which devices are theirs.

A *source* is any folder of Parquet captures in processed_parquet/ (a scripted gateway run or live
home traffic). A *profile* is a person: a name, a source, and either all devices of the source or a
set of device IPs. With a device set, the metrics are computed on that person's traffic only, so
several people behind one router are kept apart. Scripted sources may also have a plan (ground
truth, baseline and clinical phase) and expectations; live sources use the profile's own baseline
period instead.

Stored in <home>/profiles.json. If the file does not exist yet, one profile per scripted persona is
created (all devices of its source, so its numbers stay those of the evaluation).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .groundtruth import load_devices
from .partitions import list_datasets
from .personas import PERSONAS
from .settings import Settings

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


@dataclass
class Device:
    ip: str
    label: str = ""


@dataclass
class Profile:
    id: str
    name: str
    source: str
    all_devices: bool = True
    devices: list[Device] = field(default_factory=list)
    baseline_first: str | None = None    # YYYY-MM-DD; used when the source has no plan
    baseline_last: str | None = None
    persona: str | None = None           # key of the scripted persona (expectations), if any

    @property
    def device_ips(self) -> list[str]:
        return sorted({d.ip for d in self.devices})

    @property
    def view_key(self) -> str:
        """Cache key of the traffic this profile is computed on."""
        if self.all_devices or not self.devices:
            return "all"
        return "dev-" + hashlib.md5(",".join(self.device_ips).encode()).hexdigest()[:10]

    @property
    def cache_name(self) -> str:
        """Folder of this profile's day records inside the cache directory."""
        return self.source if self.view_key == "all" else f"{self.source}/@{self.view_key}"

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["view_key"] = self.view_key
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "Profile":
        devs = [Device(**x) if isinstance(x, dict) else Device(str(x)) for x in d.get("devices") or []]
        return cls(id=d["id"], name=d.get("name") or d["id"], source=d["source"],
                   all_devices=bool(d.get("all_devices", True)), devices=devs,
                   baseline_first=d.get("baseline_first"), baseline_last=d.get("baseline_last"),
                   persona=d.get("persona"))


def validate(p: Profile, sources: list[str]) -> None:
    if not _ID_RE.match(p.id):
        raise ValueError("id: lowercase letters, digits, - and _, at most 40 characters")
    if not p.name.strip():
        raise ValueError("name is required")
    if p.source not in sources:
        raise ValueError(f"unknown source {p.source!r}")
    if not p.all_devices and not p.devices:
        raise ValueError("choose at least one device, or all devices of the source")
    for d in p.devices:
        if not re.match(r"^[0-9a-fA-F:.]+$", d.ip):
            raise ValueError(f"not an IP address: {d.ip!r}")
    if bool(p.baseline_first) != bool(p.baseline_last):
        raise ValueError("baseline needs a first and a last day")
    if p.baseline_first and p.baseline_last and p.baseline_first > p.baseline_last:
        raise ValueError("baseline: first day after last day")


class ProfileStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = settings.home_dir / "profiles.json"

    def sources(self) -> list[str]:
        return list_datasets(self.settings.processed_dir)

    def _defaults(self) -> list[Profile]:
        devices = load_devices(self.settings.devices_csv)
        out = []
        for src in self.sources():
            meta = PERSONAS.get(src)
            if not meta:
                continue
            devs = [Device(ip, d.get("device", "")) for ip, d in sorted(devices.items()) if d.get("dataset") == src]
            out.append(Profile(id=meta["name"].lower(), name=meta["name"], source=src, all_devices=True,
                               devices=devs, persona=src))
        return out

    def all(self) -> list[Profile]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [Profile.from_json(d) for d in data.get("profiles", [])]
        except FileNotFoundError:
            profiles = self._defaults()
            if profiles:
                self._save(profiles)
            return profiles
        except (OSError, ValueError, KeyError):
            return []

    def get(self, pid: str) -> Profile | None:
        return next((p for p in self.all() if p.id == pid), None)

    def _save(self, profiles: list[Profile]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".tmp-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"profiles": [asdict(p) for p in profiles]}, f, indent=1)
        os.replace(tmp, self.path)

    def upsert(self, p: Profile) -> Profile:
        validate(p, self.sources())
        profiles = self.all()
        idx = next((i for i, q in enumerate(profiles) if q.id == p.id), None)
        if idx is None:
            profiles.append(p)
        else:
            profiles[idx] = p
        self._save(profiles)
        return p

    def delete(self, pid: str) -> bool:
        profiles = self.all()
        keep = [p for p in profiles if p.id != pid]
        self._save(keep)
        return len(keep) != len(profiles)
