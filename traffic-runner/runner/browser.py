"""Playwright/Chromium driver.

Every CLI run starts its own browser process with a fresh context, so no DNS, HTTP or
cookie state carries over between blocks (activity catalog §5.2). Playwright is imported
lazily so that config, tests and --dry-run work without it.
"""

from __future__ import annotations

import html
import logging
import re
import time
from urllib.parse import parse_qs, quote_plus, urlsplit

from .context import PageError

log = logging.getLogger("runner")

LAUNCH_ARGS = [
    "--autoplay-policy=no-user-gesture-required",
]
CONSENT_WAIT_MS = 1500  # banners usually appear shortly after DOMContentLoaded
SKIP_LINK_RE = re.compile(
    r"(login|logout|signin|sign-in|signup|register|account|konto|abo|subscribe|checkout|mailto:|\.pdf$)",
    re.I,
)

# Runs before any page script: ask the YouTube player for 144p via its stored preference.
YT_QUALITY_INIT = """
(() => {
  try {
    if (!/(^|\\.)youtube\\.com$/.test(location.hostname)) return;
    const now = Date.now();
    localStorage.setItem('yt-player-quality', JSON.stringify({
      data: JSON.stringify({quality: 144, previousQuality: 144}),
      expiration: now + 30 * 24 * 3600 * 1000, creation: now}));
  } catch (e) {}
})();
"""

# Re-applied while watching: pin the lowest quality and make sure the video plays.
YT_FORCE_LOW = """
() => {
  const p = document.getElementById('movie_player') || document.querySelector('.html5-video-player');
  const v = document.querySelector('video');
  if (v) { v.muted = true; if (v.paused && !v.ended) v.play().catch(() => {}); }
  if (!p) return null;
  try { if (p.setPlaybackQualityRange) p.setPlaybackQualityRange('tiny', 'tiny'); } catch (e) {}
  try { if (p.setPlaybackQuality) p.setPlaybackQuality('tiny'); } catch (e) {}
  try { return p.getPlaybackQuality ? p.getPlaybackQuality() : 'unknown'; } catch (e) { return 'unknown'; }
}
"""

MEDIA_STATE = """
() => {
  const m = document.querySelector('video, audio');
  if (!m) return 'none';
  if (m.error) return 'error';
  if (m.ended) return 'ended';
  return m.paused ? 'paused' : 'playing';
}
"""

MEDIA_STARTED = """
() => {
  const m = document.querySelector('video, audio');
  return !!m && (!!m.error || (!m.paused && m.currentTime > 0));
}
"""


def host_of(url: str) -> str:
    return urlsplit(url).hostname or ""


def site_of(host: str) -> str:
    """Last two labels, the same reduction the thesis pipeline uses."""
    return ".".join(host.split(".")[-2:])


class BrowserDriver:
    def __init__(self, playwright_device: str, context_options: dict, consent_buttons: list[str],
                 headless: bool = True):
        self.playwright_device = playwright_device
        self.context_options = dict(context_options or {})
        self.headless = headless
        self.consent_re = (
            re.compile(r"^\s*(?:" + "|".join(re.escape(b) for b in consent_buttons) + r")\s*$", re.I)
            if consent_buttons else None
        )
        self._pw = None
        self._browser = None
        self._context = None
        self.page = None
        self._error_cls = Exception

    # --- lifecycle ---
    def _ensure(self) -> None:
        if self.page is not None:
            return
        from playwright.sync_api import Error, sync_playwright

        self._error_cls = Error
        if self._pw is None:
            self._pw = sync_playwright().start()
        descriptor = dict(self._pw.devices[self.playwright_device])
        descriptor.pop("default_browser_type", None)
        self._browser = self._pw.chromium.launch(headless=self.headless, args=LAUNCH_ARGS)
        self._context = self._browser.new_context(**descriptor, **self.context_options)
        self._context.add_init_script(YT_QUALITY_INIT)
        self.page = self._context.new_page()
        self.page.set_default_timeout(15_000)
        log.debug("browser started (%s)", self.playwright_device)

    def restart(self) -> None:
        for obj in (self._context, self._browser):
            try:
                if obj is not None:
                    obj.close()
            except Exception:  # noqa: BLE001 - closing a broken browser must not fail the run
                pass
        self._context = self._browser = self.page = None

    def close(self) -> None:
        self.restart()
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
            self._pw = None

    # --- navigation ---
    def open(self, url: str, timeout: float) -> str:
        self._ensure()
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except self._error_cls as e:
            raise PageError(str(e).splitlines()[0]) from None
        self._dismiss_consent()
        return host_of(self.page.url)

    def _dismiss_consent(self) -> None:
        if self.consent_re is None:
            return
        self.page.wait_for_timeout(CONSENT_WAIT_MS)
        for frame in list(self.page.frames):
            try:
                button = frame.get_by_role("button", name=self.consent_re)
                if button.count() and button.first.is_visible():
                    button.first.click(timeout=3000)
                    log.info("cookie banner rejected on %s", host_of(frame.url) or host_of(self.page.url))
                    self.page.wait_for_load_state("domcontentloaded", timeout=10_000)
                    return
            except self._error_cls:
                continue

    def dwell(self, seconds: float, rng) -> None:
        self._ensure()
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            step = rng.uniform(1.5, 6.0)
            dy = rng.randint(200, 900)
            if rng.random() < 0.15:
                dy = -dy  # readers scroll back now and then
            try:
                self.page.evaluate("dy => window.scrollBy({top: dy, behavior: 'smooth'})", dy)
            except self._error_cls:
                pass  # page is navigating; keep waiting
            self.page.wait_for_timeout(min(step, left) * 1000)

    def follow_link(self, rng, timeout: float) -> str | None:
        if self.page is None:
            return None
        current = self.page.url.split("#")[0]
        site = site_of(host_of(current))
        try:
            hrefs = self.page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        except self._error_cls:
            return None
        candidates = sorted({
            h.split("#")[0] for h in hrefs
            if h.startswith(("http://", "https://"))
            and site_of(host_of(h)) == site
            and h.split("#")[0] != current
            and not SKIP_LINK_RE.search(h)
        })
        if not candidates:
            log.info("no internal link to follow on %s", current)
            return None
        return self.open(rng.choice(candidates), timeout)

    def idle(self, seconds: float) -> None:
        if seconds <= 0:
            return
        if self.page is not None:
            self.page.wait_for_timeout(seconds * 1000)
        else:
            time.sleep(seconds)

    # --- media ---
    def play_youtube(self, search_term: str, result_index: int, timeout: float) -> str:
        self.open("https://www.youtube.com/results?search_query=" + quote_plus(search_term), timeout)
        try:
            self.page.wait_for_selector('a[href*="/watch?v="]', state="attached", timeout=timeout * 1000)
            hrefs = self.page.eval_on_selector_all('a[href*="/watch?v="]', "els => els.map(e => e.href)")
        except self._error_cls as e:
            raise PageError(f"no YouTube search results: {str(e).splitlines()[0]}") from None
        video_ids: list[str] = []
        for h in hrefs:  # DOM order = result rank
            vid = (parse_qs(urlsplit(h).query).get("v") or [""])[0]
            if vid and vid not in video_ids:
                video_ids.append(vid)
        if not video_ids:
            raise PageError("no YouTube search results")
        vid = video_ids[min(result_index, len(video_ids) - 1)]
        host = self.open(f"https://{host_of(self.page.url)}/watch?v={vid}", timeout)
        quality = None
        for _ in range(10):  # the player object appears a few seconds after load
            quality = self.page.evaluate(YT_FORCE_LOW)
            if quality:
                break
            self.page.wait_for_timeout(2000)
        log.info("YouTube video %s, playback quality: %s", vid, quality or "unknown (no player)")
        return host

    def play_audio(self, url: str, timeout: float) -> str:
        self._ensure()
        self.page.goto("about:blank")
        self.page.set_content(f'<audio src="{html.escape(url)}" autoplay></audio>')
        try:
            self.page.wait_for_function(MEDIA_STARTED, timeout=timeout * 1000)
        except self._error_cls:
            raise PageError(f"audio stream did not start: {url}") from None
        if self.media_state() == "error":
            raise PageError(f"audio stream cannot be decoded: {url}")
        return host_of(url)

    def media_state(self) -> str:
        if self.page is None:
            return "none"
        try:
            if site_of(host_of(self.page.url)) == "youtube.com":
                self.page.evaluate(YT_FORCE_LOW)  # quality can reset after ads
            return self.page.evaluate(MEDIA_STATE)
        except self._error_cls:
            return "none"  # page was navigating (e.g. YouTube autoplay)

    def resume_media(self) -> None:
        try:
            dialog = self.page.get_by_role("button", name=re.compile(r"^\s*(Yes|Ja)\s*$", re.I))
            if dialog.count() and dialog.first.is_visible():
                dialog.first.click(timeout=3000)  # "Video paused. Continue watching?"
            self.page.evaluate("() => { const m = document.querySelector('video, audio'); if (m) m.play().catch(() => {}); }")
        except self._error_cls:
            pass
