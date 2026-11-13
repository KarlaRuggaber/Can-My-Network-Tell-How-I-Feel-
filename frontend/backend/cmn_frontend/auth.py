"""Logins: a local users file with hashed passwords, and signed session cookies.

    python -m cmn_frontend.users add anna --role single --profile ben
    python -m cmn_frontend.users add dr-meier --role multi --profiles all

Roles:
- "single": sees exactly one person profile (the simple view).
- "multi":  clinicians, parents: choose between their profiles and configure which devices
            belong to which person.

The users file (<home>/users.json) and the session key (<home>/session.key) stay on this machine;
neither is in git. Passwords are stored as scrypt hashes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROLES = ("single", "multi")
SESSION_COOKIE = "cmn_session"
SESSION_SECONDS = 12 * 3600


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        kind, salt, digest = stored.split("$")
    except ValueError:
        return False
    if kind != "scrypt":
        return False
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), stored)


@dataclass
class User:
    username: str
    role: str                     # "single" | "multi"
    profiles: list[str] = field(default_factory=list)   # profile ids; ["*"] = all (multi only)
    password_hash: str = ""

    def can_see(self, profile_id: str) -> bool:
        return "*" in self.profiles or profile_id in self.profiles

    def public(self) -> dict[str, Any]:
        return {"username": self.username, "role": self.role, "profiles": self.profiles}


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


class UserStore:
    def __init__(self, home: Path):
        self.path = Path(home) / "users.json"

    def all(self) -> list[User]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [User(**u) for u in data.get("users", [])]

    def get(self, username: str) -> User | None:
        return next((u for u in self.all() if u.username == username), None)

    def _save(self, users: list[User]) -> None:
        _write_json(self.path, {"users": [asdict(u) for u in users]})

    def add(self, username: str, password: str, role: str, profiles: list[str]) -> User:
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}")
        if not username or not password:
            raise ValueError("username and password are required")
        if role == "single" and (len(profiles) != 1 or profiles == ["*"]):
            raise ValueError("a single-profile user needs exactly one profile")
        users = [u for u in self.all() if u.username != username]
        user = User(username, role, list(profiles), hash_password(password))
        self._save(users + [user])
        return user

    def set_password(self, username: str, password: str) -> None:
        users = self.all()
        for u in users:
            if u.username == username:
                u.password_hash = hash_password(password)
                self._save(users)
                return
        raise KeyError(username)

    def grant(self, username: str, profile_id: str) -> None:
        users = self.all()
        for u in users:
            if u.username == username and profile_id not in u.profiles:
                u.profiles.append(profile_id)
        self._save(users)

    def remove(self, username: str) -> bool:
        users = self.all()
        keep = [u for u in users if u.username != username]
        self._save(keep)
        return len(keep) != len(users)

    def verify(self, username: str, password: str) -> User | None:
        u = self.get(username)
        if u is None:
            hash_password(password)       # same work for unknown users
            return None
        return u if check_password(password, u.password_hash) else None


def _session_key(home: Path) -> bytes:
    p = Path(home) / "session.key"
    try:
        return p.read_bytes()
    except OSError:
        p.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(key)
        return key


def make_session(home: Path, username: str, now: float | None = None) -> str:
    body = base64.urlsafe_b64encode(json.dumps(
        {"u": username, "exp": int((now or time.time()) + SESSION_SECONDS)}).encode()).decode()
    sig = hmac.new(_session_key(home), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_session(home: Path, token: str | None, now: float | None = None) -> str | None:
    """Username of a valid, unexpired session token, else None."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    good = hmac.new(_session_key(home), body.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, good):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body.encode()))
    except ValueError:
        return None
    if data.get("exp", 0) < (now or time.time()):
        return None
    return data.get("u")
