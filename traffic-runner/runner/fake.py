"""Network-free driver and clock for tests and `--dry-run`.

The fake driver records every call and advances a fake clock instead of waiting, so a
30-minute activity "runs" in milliseconds and two runs can be compared call by call.
"""

from __future__ import annotations

from urllib.parse import urlsplit

LOAD_TIME = 2.0  # simulated seconds per page load
FAKE_LINKS = 12  # same-site links every fake page offers


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.t = start

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += max(0.0, seconds)


class FakeDriver:
    def __init__(self, clock: FakeClock, media_length: float | None = None):
        self.clock = clock
        self.calls: list[tuple] = []
        self.url: str | None = None
        self.media_length = media_length  # seconds until media 'ends'; None = endless
        self._media_started: float | None = None

    def _load(self, url: str, timeout: float) -> str:
        self.clock.sleep(min(LOAD_TIME, timeout))
        self.url = url
        return urlsplit(url).hostname or ""

    def open(self, url, timeout):
        self.calls.append(("open", url))
        return self._load(url, timeout)

    def dwell(self, seconds, rng):
        # Consume the scroll RNG like the real driver would, to keep the comparison honest.
        scrolls = []
        t = 0.0
        while t < seconds:
            step = rng.uniform(1.5, 6.0)
            dy = rng.randint(200, 900)
            scrolls.append(-dy if rng.random() < 0.15 else dy)
            t += step
        self.calls.append(("dwell", round(seconds, 3), len(scrolls)))
        self.clock.sleep(seconds)

    def scroll_feed(self, seconds, rng):
        loads = 0
        t = 0.0
        while t < seconds:
            t += rng.uniform(5.0, 15.0)
            loads += 1
        self.calls.append(("feed", round(seconds, 3), loads))
        self.clock.sleep(seconds)

    def download(self, page_url, file_url, timeout):
        host = self._load(page_url, timeout)
        self.calls.append(("download", file_url))
        self.clock.sleep(min(3.0, timeout))
        return host

    def dns_lookup(self, name):
        self.calls.append(("dns", name))
        return False

    def follow_link(self, rng, timeout):
        if not self.url:
            return None
        host = urlsplit(self.url).hostname
        links = sorted(f"https://{host}/link{i}" for i in range(FAKE_LINKS))
        target = rng.choice(links)
        self.calls.append(("follow", target))
        return self._load(target, timeout)

    def idle(self, seconds):
        self.calls.append(("idle", round(seconds, 3)))
        self.clock.sleep(seconds)

    def new_context(self):
        self.calls.append(("new_context",))
        self.url = None

    def restart(self):
        self.calls.append(("restart",))
        self.url = None

    def play_youtube(self, search_term, result_index, timeout):
        self.calls.append(("youtube", search_term, result_index))
        self._media_started = self.clock.now()
        return self._load("https://www.youtube.com/watch?v=fake", timeout)

    def play_srf(self, start_url, result_index, timeout):
        self.calls.append(("srf", start_url, result_index))
        self._media_started = self.clock.now()
        return self._load("https://www.srf.ch/play/tv/fake/video/fake", timeout)

    def play_audio(self, url, timeout):
        self.calls.append(("audio", url))
        self._media_started = self.clock.now()
        return self._load(url, timeout)

    def play_audio_page(self, url, timeout):
        self.calls.append(("audio_page", url))
        self._media_started = self.clock.now()
        return self._load(url, timeout)

    def join_call(self, url, timeout):
        self.calls.append(("call", url.split("#")[0]))
        self._media_started = self.clock.now()
        return self._load(url, timeout)

    def send_message(self, text):
        self.calls.append(("message", text))
        self.clock.sleep(len(text) * 0.06)

    def recover(self):
        self.calls.append(("recover",))
        self.url = None

    webhook_channel_id = ""  # channel the fake Discord reports; tests and --dry-run set it

    def webhook_post(self, url, image, content, timeout):
        import os
        from .discord import webhook_id
        size = os.path.getsize(image)
        hook = webhook_id(url)
        self.calls.append(("webhook_post", hook, content, size))
        self.clock.sleep(min(LOAD_TIME, timeout))
        channel = self.webhook_channel_id
        return {"id": "1", "webhook_id": hook, "channel_id": channel,
                "attachments": [{"size": size, "url": f"https://cdn.discordapp.com/attachments/{channel}/1/test.png"}]}

    def set_mic(self, on):
        self.calls.append(("mic", on))

    def play_game(self, url, timeout):
        self.calls.append(("game", url))
        self._media_started = self.clock.now()
        return self._load(url, timeout)

    def media_state(self):
        if self._media_started is None:
            return "none"
        if self.media_length is not None and self.clock.now() - self._media_started >= self.media_length:
            return "ended"
        return "playing"

    def resume_media(self):
        self.calls.append(("resume",))

    def close(self):
        self.calls.append(("close",))
