"""Day notes and "seen" marks for flags, written by clinicians and parents (multi-profile users).

Notes give the context the network cannot see ("holidays", "exam week", "moved to outpatient
care"), so a different day can be read correctly. A flag marked as seen stays visible but muted until
a new day joins it. Stored in <home>/notes.json (owner-only, like the other portal files).
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_NOTE = 2000
_lock = threading.Lock()


class NoteStore:
    def __init__(self, home: Path):
        self.path = Path(home) / "notes.json"

    def _load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"notes": {}, "seen": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".tmp-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    # ---- notes ----

    def notes(self, profile: str) -> list[dict[str, Any]]:
        out = [n for day in self._load().get("notes", {}).get(profile, {}).values() for n in day]
        return sorted(out, key=lambda n: (n["date"], n["created"]))

    def add(self, profile: str, day: str, text: str, author: str) -> dict[str, Any]:
        text = text.strip()
        if not text:
            raise ValueError("the note is empty")
        if len(text) > MAX_NOTE:
            raise ValueError(f"notes are limited to {MAX_NOTE} characters")
        note = {"id": secrets.token_hex(6), "date": day, "text": text, "author": author,
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with _lock:
            data = self._load()
            data.setdefault("notes", {}).setdefault(profile, {}).setdefault(day, []).append(note)
            self._save(data)
        return note

    def delete(self, profile: str, note_id: str) -> bool:
        with _lock:
            data = self._load()
            days = data.get("notes", {}).get(profile, {})
            for day, lst in list(days.items()):
                keep = [n for n in lst if n["id"] != note_id]
                if len(keep) != len(lst):
                    if keep:
                        days[day] = keep
                    else:
                        del days[day]
                    self._save(data)
                    return True
        return False

    # ---- flags marked as seen ----

    def seen(self, profile: str) -> dict[str, dict[str, Any]]:
        return self._load().get("seen", {}).get(profile, {})

    def mark_seen(self, profile: str, flag_id: str, last_day: str, author: str) -> dict[str, Any]:
        mark = {"last_day": last_day, "by": author,
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with _lock:
            data = self._load()
            data.setdefault("seen", {}).setdefault(profile, {})[flag_id] = mark
            self._save(data)
        return mark

    def unmark_seen(self, profile: str, flag_id: str) -> None:
        with _lock:
            data = self._load()
            data.get("seen", {}).get(profile, {}).pop(flag_id, None)
            self._save(data)
