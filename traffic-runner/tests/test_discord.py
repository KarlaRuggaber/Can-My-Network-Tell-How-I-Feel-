"""runner/discord.py without network: URL checks, webhook file, multipart request, errors."""

import email.parser
import io
import json
import urllib.error

import pytest

from runner import discord
from runner.context import NotImplementedActivity, PageError

HOOK_ID, CHANNEL_ID = "123456789012345678", "987654321098765432"
TOKEN = "abcdefghijklmnopqrstuvwxyz0123456789-_AB"
URL = f"https://discord.com/api/webhooks/{HOOK_ID}/{TOKEN}"
CFG = {"webhook_id": HOOK_ID, "channel_id": CHANNEL_ID}


@pytest.mark.parametrize("url, ok", [
    (URL, True),
    (f"https://discord.com/api/v10/webhooks/{HOOK_ID}/{TOKEN}", True),
    (f"https://discordapp.com/api/webhooks/{HOOK_ID}/{TOKEN}", True),
    (f"http://discord.com/api/webhooks/{HOOK_ID}/{TOKEN}", False),                # no TLS
    (f"https://discord.com.evil.example/api/webhooks/{HOOK_ID}/{TOKEN}", False),  # lookalike host
    (f"https://evil.example/discord.com/api/webhooks/{HOOK_ID}/{TOKEN}", False),
    (f"https://discord.com/api/webhooks/{HOOK_ID}", False),                       # no token
    (f"https://discord.com/api/webhooks/{HOOK_ID}/{TOKEN}/slack", False),         # other endpoint
    (f"https://discord.com/api/channels/{HOOK_ID}/messages", False),
])
def test_webhook_url_check(url, ok):
    if ok:
        assert discord.webhook_id(url) == HOOK_ID
    else:
        with pytest.raises(ValueError):
            discord.webhook_id(url)


def test_load_webhook(tmp_path):
    with pytest.raises(NotImplementedActivity, match="not configured"):
        discord.load_webhook({"webhook_id": "", "channel_id": ""}, tmp_path)
    with pytest.raises(NotImplementedActivity, match="no Discord webhook file"):
        discord.load_webhook(CFG, tmp_path)
    (tmp_path / discord.WEBHOOK_FILE).write_text(URL + "\n")
    assert discord.load_webhook(CFG, tmp_path) == URL
    other = f"https://discord.com/api/webhooks/111111111111111111/{TOKEN}"
    (tmp_path / discord.WEBHOOK_FILE).write_text(other)
    with pytest.raises(PageError, match="allows only"):  # a webhook of another channel/server
        discord.load_webhook(CFG, tmp_path)
    (tmp_path / discord.WEBHOOK_FILE).write_text("https://hooks.slack.com/services/T/B/x")
    with pytest.raises(PageError, match="not a Discord webhook"):
        discord.load_webhook(CFG, tmp_path)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def message(size):
    return {"id": "42", "webhook_id": HOOK_ID, "channel_id": CHANNEL_ID,
            "attachments": [{"size": size, "url": "https://cdn.discordapp.com/attachments/1/2/test.png"}]}


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "test.png"
    path.write_bytes(b"\x89PNG" + bytes(range(256)) * 40)
    return path


def test_post_image_sends_one_multipart_request(image):
    sent = []

    def opener(req, timeout):
        sent.append((req, timeout))
        return FakeResponse(json.dumps(message(image.stat().st_size)).encode())

    msg = discord.post_image(URL, str(image), "Test upload 1234", 30, opener=opener)
    assert msg["id"] == "42"
    (req, timeout), = sent
    assert req.full_url == URL + "?wait=true" and req.get_method() == "POST" and timeout == 30
    assert req.get_header("User-agent") == discord.USER_AGENT
    # Parse the body like a server would and check both parts.
    raw = b"Content-Type: " + req.get_header("Content-type").encode() + b"\r\n\r\n" + req.data
    parts = {p.get_param("name", header="content-disposition"): p
             for p in email.parser.BytesParser().parsebytes(raw).get_payload()}
    payload = json.loads(parts["payload_json"].get_payload(decode=True))
    assert payload["content"] == "Test upload 1234"
    assert payload["allowed_mentions"] == {"parse": []}  # never pings anyone
    assert parts["files[0]"].get_filename() == "test.png"
    assert parts["files[0]"].get_payload(decode=True) == image.read_bytes()


def test_post_image_refuses_non_webhook_url(image):
    with pytest.raises(ValueError):
        discord.post_image("https://example.com/upload", str(image), "x", 30, opener=None)


def http_error(code, body):
    return urllib.error.HTTPError(URL, code, "error", {}, io.BytesIO(json.dumps(body).encode()))


def test_post_image_retries_once_after_short_rate_limit(image):
    answers = [http_error(429, {"retry_after": 1.5}), FakeResponse(json.dumps(message(image.stat().st_size)).encode())]
    slept = []

    def opener(req, timeout):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    assert discord.post_image(URL, str(image), "x", 30, opener=opener, sleep=slept.append)["id"] == "42"
    assert slept == [1.5]


def test_post_image_long_rate_limit_and_other_errors_fail(image):
    def opener_for(err):
        def opener(req, timeout):
            raise err
        return opener

    with pytest.raises(PageError, match="HTTP 429"):
        discord.post_image(URL, str(image), "x", 30, opener=opener_for(http_error(429, {"retry_after": 60})),
                           sleep=lambda s: None)
    with pytest.raises(PageError, match="HTTP 404"):  # webhook deleted
        discord.post_image(URL, str(image), "x", 30, opener=opener_for(http_error(404, {"message": "Unknown Webhook"})))
    with pytest.raises(PageError, match="not reachable"):
        discord.post_image(URL, str(image), "x", 30, opener=opener_for(urllib.error.URLError("timed out")))


def test_post_image_checks_the_attachment(image):
    def opener(req, timeout):
        return FakeResponse(json.dumps(message(5)).encode())  # Discord stored a different file

    with pytest.raises(PageError, match="no attachment"):
        discord.post_image(URL, str(image), "x", 30, opener=opener)
