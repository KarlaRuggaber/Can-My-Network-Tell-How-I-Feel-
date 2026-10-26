"""Run context: deadline, page driver and the list of visited hosts for one activity run.

Activities only talk to the RunContext. The context forwards to a driver (the real
Playwright browser, or runner.fake.FakeDriver in tests and --dry-run) and makes sure no
call runs past the deadline.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Protocol

log = logging.getLogger("runner")

NAV_TIMEOUT = 45.0  # seconds, capped by the remaining time
DISCORD_HOST = "discord.com"  # social_post upload target (runner/discord.py)
MIN_NAV_TIME = 10.0  # do not start a navigation with less time left than this (mobile pages need ~5-10 s)
STEP_SLACK = 30.0    # a step may take this much longer than planned before it counts as hung
QUICK_STEP = 30.0    # limit for short steps (media state, mic, browser start)
RECOVER_LIMIT = 20.0  # limit for restarting Playwright after a hung step


class PageError(RuntimeError):
    """A page could not be loaded (timeout, DNS/TLS error, ...). Not fatal for a run."""


class MediaStalled(PageError):
    """Media stopped playing for three checks in a row (watch_media)."""


class StepTimeout(PageError):
    """A single browser step took longer than its limit: the page or browser hangs (runner/steps.py)."""


def site_of(host: str | None) -> str:
    """Last two labels of a host, the same reduction the thesis pipeline uses."""
    return ".".join((host or "").split(".")[-2:])


def host_of(url: str) -> str:
    from urllib.parse import urlsplit
    return urlsplit(url).hostname or ""


class NotImplementedActivity(RuntimeError):
    """Activity exists in the catalog but is not implemented (e.g. needs test accounts)."""


class Clock(Protocol):
    def now(self) -> float: ...
    def sleep(self, seconds: float) -> None: ...


class RealClock:
    def now(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class Driver(Protocol):
    """What an activity can do with the browser. All durations in seconds."""

    def open(self, url: str, timeout: float) -> str:
        """Load url as main document; return the final host. Raises PageError."""

    def dwell(self, seconds: float, rng: random.Random) -> None:
        """Stay on the current page for `seconds`, scrolling like a reader."""

    def scroll_feed(self, seconds: float, rng: random.Random) -> None:
        """Scroll an endless feed for `seconds`, loading more content every 5-15 s."""

    def download(self, page_url: str, file_url: str, timeout: float) -> str:
        """Open page_url and download file_url from it completely; return the page host."""

    def dns_lookup(self, name: str) -> bool:
        """DNS lookup only, no connection. True if the name resolved."""

    def follow_link(self, rng: random.Random, timeout: float) -> str | None:
        """Open one same-site link of the current page; return its host or None."""

    def idle(self, seconds: float) -> None:
        """Let time pass without interacting (page, if any, stays open)."""

    def restart(self) -> None:
        """Close the browser; the next call starts a fresh one (no DNS/HTTP cache)."""

    def new_context(self) -> None:
        """Close the browser context; the next call opens a new one (no cookies, DNS/HTTP cache)."""

    def play_youtube(self, search_term: str, result_index: int, timeout: float) -> str:
        """Search YouTube, play the n-th result at the lowest quality; return host."""

    def play_srf(self, start_url: str, result_index: int, timeout: float) -> str:
        """Open SRF Play, play the n-th on-demand video at the lowest quality; return host."""

    def play_audio(self, url: str, timeout: float) -> str:
        """Play an audio stream URL; return its host."""

    def play_audio_page(self, url: str, timeout: float) -> str:
        """Open a radio page that plays a live stream, at the lowest quality; return host."""

    def join_call(self, url: str, timeout: float) -> str:
        """Open a call room and wait until the media connection is up; return host."""

    def set_mic(self, on: bool) -> None:
        """Mute or unmute the microphone in the running call."""

    def send_message(self, text: str) -> None:
        """Type and send a message in the open chat. Raises PageError."""

    def webhook_post(self, url: str, image: str, content: str, timeout: float) -> dict:
        """Post the image through a Discord webhook; return Discord's message object. Raises PageError."""

    def play_game(self, url: str, timeout: float) -> str:
        """Open the game page and wait until it is connected; return host."""

    def media_state(self) -> str:
        """'playing', 'paused', 'stalled' (no data), 'ended', 'error' or 'none'. After
        join_call/play_game it reports the call or game connection instead of a media element."""

    def resume_media(self) -> None:
        """Try to continue playback after a pause prompt."""

    def recover(self) -> None:
        """After a hung step: drop the browser (stop Playwright, kill leftovers); the next call starts fresh."""

    def close(self) -> None: ...


class RunContext:
    def __init__(self, driver: Driver, clock: Clock, duration: float, overrides: dict | None = None):
        self.driver = driver
        self.clock = clock
        self.duration = duration
        self.start = clock.now()
        self.deadline = self.start + duration
        self.overrides = overrides or {}
        self.visited: list[str] = []
        self.page_errors = 0
        self.run_key = ""  # profile/seed/block_id, set by the CLI (call room names)
        self.session_meta: dict = {}  # meta of the device's login session (runner/sessions.py)
        self.accounts: dict = {}  # config/accounts.yaml
        self.webhook_url = ""  # social_post: Discord webhook (runner/discord.py), set by the CLI
        self._bad_checks = 0
        # Step limits (runner/steps.py Guard, set by the CLI; None in tests and --dry-run).
        self.guard = None
        self.hung_sites: set[str] = set()  # sites (last two labels) that hung in this run
        self._hung = False  # a step hung since the activity last asked (take_hung)
        self._host = ""  # host of the current page, for marking hung sites

    # --- step limits ---
    def _limit(self, expected: float) -> float:
        return expected + STEP_SLACK

    def _call(self, limit: float, what: str, fn, *args):
        """Run one driver call under a time limit. A call that hangs restarts Playwright, marks
        the current site as hung and raises StepTimeout (a PageError)."""
        if self.guard is None:
            return fn(*args)
        try:
            with self.guard.limit(limit, what):
                return fn(*args)
        except StepTimeout:
            site = site_of(self._host)
            if site:
                self.hung_sites.add(site)
            self._hung = True
            self.page_errors += 1
            log.warning("%s hung for %.0f s on %s, restarting the browser", what, limit, self._host or "?")
            try:
                with self.guard.limit(RECOVER_LIMIT, "browser restart"):
                    self.driver.recover()
            except StepTimeout:
                log.error("browser restart hung too")
            raise

    def take_hung(self) -> bool:
        """True once after a step hung: the activity should leave the current site."""
        hung, self._hung = self._hung, False
        return hung

    # --- time ---
    def elapsed(self) -> float:
        return self.clock.now() - self.start

    def remaining(self) -> float:
        return max(0.0, self.deadline - self.clock.now())

    def idle(self, seconds: float) -> None:
        left = min(seconds, self.remaining())
        try:
            self._call(self._limit(left), "idle", self.driver.idle, left)
        except StepTimeout:
            pass

    def sleep_without_browser(self, seconds: float) -> None:
        self.clock.sleep(min(seconds, self.remaining()))

    # --- catalog overrides (`pages`, `dwell` from the profile, §1 "Frequency keys") ---
    def range(self, name: str, default: tuple[float, float]) -> tuple[float, float]:
        return self.overrides.get(name) or default

    # --- page actions ---
    def _record(self, host: str | None) -> str | None:
        if host:
            self._host = host
        if host and host not in self.visited:
            self.visited.append(host)
        return host

    def _nav_timeout(self) -> float | None:
        left = self.remaining()
        return None if left < MIN_NAV_TIME else min(NAV_TIMEOUT, left)

    def open(self, url: str) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        self._host = host_of(url)  # a hang during the load belongs to this site
        try:
            return self._record(self._call(self._limit(timeout), "page load", self.driver.open, url, timeout))
        except PageError as e:
            self.page_errors += 1
            log.warning("could not load %s: %s", url, e)
            return None

    def dwell(self, seconds: float, seed: float) -> None:
        left = min(seconds, self.remaining())
        if left > 0:
            try:
                self._call(self._limit(left), "dwell", self.driver.dwell, left, random.Random(seed))
            except StepTimeout:
                pass

    def scroll_feed(self, seconds: float, seed) -> None:
        left = min(seconds, self.remaining())
        if left > 0:
            try:
                self._call(self._limit(left), "feed scroll", self.driver.scroll_feed, left, random.Random(seed))
            except StepTimeout:
                pass

    def download(self, page_url: str, file_url: str) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        try:
            self._host = host_of(page_url)
            return self._record(self._call(self._limit(2 * timeout), "download", self.driver.download, page_url, file_url, timeout))
        except PageError as e:
            self.page_errors += 1
            log.warning("%s", e)
            return None

    def dns_lookup(self, name: str) -> bool:
        """Records the queried name as visited, whether it resolves or not."""
        self._record(name)
        return self.driver.dns_lookup(name)

    def follow_link(self, seed: float) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        try:
            return self._record(self._call(self._limit(timeout), "link", self.driver.follow_link, random.Random(seed), timeout))
        except PageError as e:
            self.page_errors += 1
            log.warning("could not follow link: %s", e)
            return None

    def fresh_browser(self) -> None:
        try:
            self._call(QUICK_STEP, "browser restart", self.driver.restart)
        except StepTimeout:
            pass

    def fresh_context(self) -> None:
        try:
            self._call(QUICK_STEP, "new context", self.driver.new_context)
        except StepTimeout:
            pass

    def play_youtube(self, search_term: str, result_index: int) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        self._host = "www.youtube.com"
        return self._record(self._call(self._limit(2 * timeout), "play_youtube", self.driver.play_youtube, search_term, result_index, timeout))

    def play_srf(self, start_url: str, result_index: int) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        self._host = host_of(start_url)
        return self._record(self._call(self._limit(2 * timeout), "play_srf", self.driver.play_srf, start_url, result_index, timeout))

    def play_audio(self, url: str) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        self._host = host_of(url)
        return self._record(self._call(self._limit(2 * timeout), "play_audio", self.driver.play_audio, url, timeout))

    def play_audio_page(self, url: str) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        self._host = host_of(url)
        return self._record(self._call(self._limit(2 * timeout), "play_audio_page", self.driver.play_audio_page, url, timeout))

    def join_call(self, url: str) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        self._host = host_of(url)
        return self._record(self._call(self._limit(2 * timeout), "join_call", self.driver.join_call, url, timeout))

    def play_game(self, url: str) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        self._host = host_of(url)
        return self._record(self._call(self._limit(2 * timeout), "play_game", self.driver.play_game, url, timeout))

    def watch_media(self, check_every: float = 15.0, max_seconds: float | None = None) -> str:
        """Keep media playing until it ends, the deadline, or `max_seconds`; return the last state.

        A missing player, no data ('stalled'), a pause that resume_media() could not undo or a
        media error is tolerated for two checks in a row (buffering, YouTube switching to the
        next video); the third one fails the run. The count carries over between calls, so a
        call watched in short pieces (mic schedule) still fails after three bad checks.
        """
        stop_at = None if max_seconds is None else self.clock.now() + max_seconds
        state = "playing"
        while self.remaining() > 0:
            left = self.remaining() if stop_at is None else min(self.remaining(), stop_at - self.clock.now())
            if left <= 0:
                break
            self.idle(min(check_every, left))
            if self.remaining() <= 0:
                break
            try:
                state = self._call(QUICK_STEP, "media check", self.driver.media_state)
            except StepTimeout:
                state = "none"  # Playwright was restarted, the player is gone
            if state == "ended":
                log.info("media ended after %.0f s", self.elapsed())
                break
            if state == "paused":
                try:
                    self._call(QUICK_STEP, "resume", self.driver.resume_media)
                except StepTimeout:
                    pass
            if state in ("error", "none", "stalled", "paused"):
                self._bad_checks += 1
                if self._bad_checks >= 3:
                    self._bad_checks = 0  # a caller that recovers (video_stream) starts fresh
                    raise MediaStalled(f"media stopped playing (state={state})")
            else:
                self._bad_checks = 0
        return state

    def set_mic(self, on: bool) -> None:
        self._call(QUICK_STEP, "mic", self.driver.set_mic, on)

    def send_message(self, text: str) -> None:
        self._call(QUICK_STEP + len(text), "message", self.driver.send_message, text)

    def webhook_post(self, image, content: str) -> dict | None:
        """Post through the Discord webhook and check that the message landed in exactly the
        configured channel (accounts.yaml discord.channel_id / webhook_id). None if no time is left."""
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        cfg = self.accounts.get("discord") or {}
        self._host = DISCORD_HOST
        msg = self._call(self._limit(timeout), "upload", self.driver.webhook_post, self.webhook_url, str(image), content, timeout)
        if (str(msg.get("channel_id")) != str(cfg.get("channel_id"))
                or str(msg.get("webhook_id")) != str(cfg.get("webhook_id"))):
            raise PageError(f"Discord message {msg.get('id')} landed in channel {msg.get('channel_id')} "
                            f"(webhook {msg.get('webhook_id')}), expected {cfg.get('channel_id')}")
        self._record(DISCORD_HOST)
        return msg
