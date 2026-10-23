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
MIN_NAV_TIME = 10.0  # do not start a navigation with less time left than this (mobile pages need ~5-10 s)


class PageError(RuntimeError):
    """A page could not be loaded (timeout, DNS/TLS error, ...). Not fatal for a run."""


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

    def follow_link(self, rng: random.Random, timeout: float) -> str | None:
        """Open one same-site link of the current page; return its host or None."""

    def idle(self, seconds: float) -> None:
        """Let time pass without interacting (page, if any, stays open)."""

    def restart(self) -> None:
        """Close the browser; the next call starts a fresh one (no DNS/HTTP cache)."""

    def play_youtube(self, search_term: str, result_index: int, timeout: float) -> str:
        """Search YouTube, play the n-th result at the lowest quality; return host."""

    def play_srf(self, start_url: str, result_index: int, timeout: float) -> str:
        """Open SRF Play, play the n-th on-demand video at the lowest quality; return host."""

    def play_audio(self, url: str, timeout: float) -> str:
        """Play an audio stream URL; return its host."""

    def play_audio_page(self, url: str, timeout: float) -> str:
        """Open a radio page that plays a live stream, at the lowest quality; return host."""

    def media_state(self) -> str:
        """'playing', 'paused', 'stalled' (no data), 'ended', 'error' or 'none'."""

    def resume_media(self) -> None:
        """Try to continue playback after a pause prompt."""

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

    # --- time ---
    def elapsed(self) -> float:
        return self.clock.now() - self.start

    def remaining(self) -> float:
        return max(0.0, self.deadline - self.clock.now())

    def idle(self, seconds: float) -> None:
        self.driver.idle(min(seconds, self.remaining()))

    def sleep_without_browser(self, seconds: float) -> None:
        self.clock.sleep(min(seconds, self.remaining()))

    # --- catalog overrides (`pages`, `dwell` from the profile, §1 "Frequency keys") ---
    def range(self, name: str, default: tuple[float, float]) -> tuple[float, float]:
        return self.overrides.get(name) or default

    # --- page actions ---
    def _record(self, host: str | None) -> str | None:
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
        try:
            return self._record(self.driver.open(url, timeout))
        except PageError as e:
            self.page_errors += 1
            log.warning("could not load %s: %s", url, e)
            return None

    def dwell(self, seconds: float, seed: float) -> None:
        left = min(seconds, self.remaining())
        if left > 0:
            self.driver.dwell(left, random.Random(seed))

    def follow_link(self, seed: float) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        try:
            return self._record(self.driver.follow_link(random.Random(seed), timeout))
        except PageError as e:
            self.page_errors += 1
            log.warning("could not follow link: %s", e)
            return None

    def fresh_browser(self) -> None:
        self.driver.restart()

    def play_youtube(self, search_term: str, result_index: int) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        return self._record(self.driver.play_youtube(search_term, result_index, timeout))

    def play_srf(self, start_url: str, result_index: int) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        return self._record(self.driver.play_srf(start_url, result_index, timeout))

    def play_audio(self, url: str) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        return self._record(self.driver.play_audio(url, timeout))

    def play_audio_page(self, url: str) -> str | None:
        timeout = self._nav_timeout()
        if timeout is None:
            return None
        return self._record(self.driver.play_audio_page(url, timeout))

    def watch_media(self, check_every: float = 15.0) -> str:
        """Keep media playing until it ends or the deadline; return the last state.

        A missing player, no data ('stalled'), a pause that resume_media() could not undo or a
        media error is tolerated for two checks in a row (buffering, YouTube switching to the
        next video); the third one fails the run.
        """
        state = "playing"
        bad = 0
        while self.remaining() > 0:
            self.idle(check_every)
            if self.remaining() <= 0:
                break
            state = self.driver.media_state()
            if state == "ended":
                log.info("media ended after %.0f s", self.elapsed())
                break
            if state == "paused":
                self.driver.resume_media()
            if state in ("error", "none", "stalled", "paused"):
                bad += 1
                if bad >= 3:
                    raise PageError(f"media stopped playing (state={state})")
            else:
                bad = 0
        return state
