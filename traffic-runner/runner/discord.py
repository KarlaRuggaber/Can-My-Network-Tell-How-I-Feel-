"""Discord webhook posting for social_post (decided 25.10, replaces Reddit).

Reddit flagged the shared account u/CMNTHIF as automated on 25.10 and blocks posting until the
account is verified as human or registered as an app; API access needs an approval with no
timeline (Responsible Builder Policy). A Discord webhook is Discord's own mechanism for
automated posts: no bot account, no approval, and discord.com is in the thesis SOCIAL list.

The webhook belongs to one channel of the project's private server. Its URL contains the
secret token, so it is a file on the gateway, like the login sessions:
    $RUNNER_SESSION_DIR/discord.webhook      one line: https://discord.com/api/webhooks/<id>/<token>
config/accounts.yaml holds the non-secret IDs (webhook_id, channel_id). The URL must carry
exactly that webhook ID, and Discord's reply must name exactly that channel, otherwise the
run is an error: social_post never posts anywhere else.

The request is sent from the device container with the standard library, so the upload
leaves from the device's IP and shows up in the capture as traffic to discord.com.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from . import sessions
from .context import NotImplementedActivity, PageError

HOST = "discord.com"
WEBHOOK_FILE = "discord.webhook"
USER_AGENT = "CMNTHIF-traffic-runner (+https://github.com/KarlaRuggaber/Can-My-Network-Tell-How-I-Feel-)"
URL_RE = re.compile(r"^https://(?:discord\.com|discordapp\.com)/api(?:/v\d+)?/webhooks/(\d{5,25})/([A-Za-z0-9_-]{20,})$")
MAX_RETRY_AFTER = 10.0  # seconds; a longer rate limit fails the block instead of waiting


def webhook_id(url: str) -> str:
    """The webhook ID in a webhook URL. ValueError if the URL is not a Discord webhook URL."""
    m = URL_RE.match(url.strip())
    if not m:
        raise ValueError("not a Discord webhook URL (https://discord.com/api/webhooks/<id>/<token>)")
    return m.group(1)


def load_webhook(cfg: dict, base: Path | None = None) -> str:
    """Webhook URL from the session folder, checked against accounts.yaml (discord.webhook_id).

    NotImplementedActivity if the server is not set up yet (no IDs or no file), like a missing
    login session. PageError if the file holds another webhook than the configured one.
    """
    expected = str(cfg.get("webhook_id") or "")
    if not expected or not cfg.get("channel_id"):
        raise NotImplementedActivity("Discord webhook not configured: set discord.webhook_id and "
                                     "discord.channel_id in config/accounts.yaml (traffic-runner README, test accounts)")
    path = Path(base or sessions.session_dir()) / WEBHOOK_FILE
    if not path.is_file():
        raise NotImplementedActivity(f"no Discord webhook file {path} (traffic-runner README, test accounts)")
    url = path.read_text().strip()
    try:
        found = webhook_id(url)
    except ValueError as e:
        raise PageError(f"{path}: {e}") from None
    if found != expected:
        raise PageError(f"{path} holds webhook {found}, but accounts.yaml allows only {expected}")
    return url


def multipart(fields: list[tuple[str, str | None, str, bytes]]) -> tuple[bytes, str]:
    """Encode (name, filename, content type, data) parts as multipart/form-data."""
    boundary = f"----cmnthif{uuid.uuid4().hex}"
    out = bytearray()
    for name, filename, ctype, data in fields:
        disp = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        out += f"--{boundary}\r\nContent-Disposition: {disp}\r\nContent-Type: {ctype}\r\n\r\n".encode()
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def post_image(url: str, image: str, content: str, timeout: float, opener=urllib.request.urlopen,
               sleep=time.sleep) -> dict:
    """Post `content` with the image as attachment; return Discord's message object.

    `?wait=true` makes Discord answer with the created message, so the caller can check where
    it went. One retry after a short rate limit (429), any other HTTP error is a PageError.
    """
    webhook_id(url)  # never send the image to anything but a webhook URL
    data = Path(image).read_bytes()
    payload = {"content": content, "allowed_mentions": {"parse": []},
               "attachments": [{"id": 0, "filename": "test.png"}]}
    body, ctype = multipart([("payload_json", None, "application/json", json.dumps(payload).encode()),
                             ("files[0]", "test.png", "image/png", data)])
    for attempt in (1, 2):
        req = urllib.request.Request(f"{url}?wait=true", data=body, method="POST",
                                     headers={"Content-Type": ctype, "User-Agent": USER_AGENT})
        try:
            with opener(req, timeout=timeout) as resp:
                msg = json.loads(resp.read().decode() or "{}")
            break
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")[:200]
            if e.code == 429 and attempt == 1:
                try:
                    wait = float(json.loads(text).get("retry_after", MAX_RETRY_AFTER + 1))
                except (ValueError, AttributeError):
                    wait = MAX_RETRY_AFTER + 1
                if wait <= MAX_RETRY_AFTER:
                    sleep(wait)
                    continue
            raise PageError(f"Discord webhook answered HTTP {e.code}: {text}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise PageError(f"Discord webhook not reachable: {e}") from None
    attachments = msg.get("attachments") or []
    if not attachments or int(attachments[0].get("size", -1)) != len(data):
        raise PageError(f"Discord message {msg.get('id')} has no attachment of {len(data)} bytes")
    return msg
