"""Client for the peer VM (peer-vm/): call counterpart and game server.

Configured by environment variables, which compose reads from traffic-runner/peer.env on the
gateway (root-only, not in git):
    RUNNER_PEER_URL        https://<vm-ip-with-dashes>.sslip.io
    RUNNER_PEER_TOKEN      token printed by peer-vm/setup.sh
    RUNNER_PEER_INSECURE_TLS=1   only for the local test with Caddy's internal CA
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import ssl
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from .context import NotImplementedActivity, PageError


@dataclass(frozen=True)
class Peer:
    url: str
    token: str
    insecure_tls: bool = False

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname or ""

    def room_for(self, run_key: str) -> str:
        """Room name derived from the run and the secret token: unique and not guessable."""
        return "r-" + hmac.new(self.token.encode(), run_key.encode(), hashlib.sha256).hexdigest()[:24]

    def call_url(self, room: str, video: bool, name: str, audio_muted: bool = False) -> str:
        """Same URL hash as the peer: mute state, no mobile app page. Not the prejoin page:
        switching it off in the URL makes Jitsi join without media (server setting instead)."""
        cfg = {
            "config.disableDeepLinking": True,
            # Opus DTX: a muted microphone sends ~5 packets/s instead of 50 silence packets/s
            # (Jitsi default), like Zoom/Teams when muted. Matters for --mic-share.
            "config.audioQuality.enableOpusDtx": True,
            "config.startWithAudioMuted": audio_muted,
            "config.startWithVideoMuted": not video,
            "config.startAudioOnly": not video,
            "userInfo.displayName": name,
        }
        return f"{self.url}/{room}#" + "&".join(f"{k}={quote(json.dumps(v))}" for k, v in cfg.items())

    def game_url(self, tick: int, seed: int) -> str:
        return f"{self.url}/game?tick={tick}&seed={seed}"

    def request_join(self, room: str, duration: float, video: bool, timeout: float = 15.0) -> None:
        """Ask the peer to join `room` for `duration` seconds."""
        body = json.dumps({"room": room, "duration": round(duration), "video": video}).encode()
        req = urllib.request.Request(f"{self.url}/peer/join", data=body, method="POST", headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        ctx = ssl._create_unverified_context() if self.insecure_tls else None  # noqa: S323 - local test only
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                if resp.status not in (200, 202):
                    raise PageError(f"peer refused the call: HTTP {resp.status}")
        except OSError as e:  # URLError, HTTPError, timeouts
            raise PageError(f"peer not reachable: {e}") from None


def from_env() -> Peer:
    url = os.environ.get("RUNNER_PEER_URL", "").rstrip("/")
    token = os.environ.get("RUNNER_PEER_TOKEN", "")
    if not url or not token:
        raise NotImplementedActivity("peer VM not configured (RUNNER_PEER_URL / RUNNER_PEER_TOKEN in peer.env)")
    return Peer(url, token, os.environ.get("RUNNER_PEER_INSECURE_TLS") == "1")
