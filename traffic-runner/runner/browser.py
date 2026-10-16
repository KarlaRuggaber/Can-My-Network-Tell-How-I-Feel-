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
CONSENT_WAIT_MS = 5000  # banners can appear a few seconds after DOMContentLoaded
CONSENT_POLL_MS = 500
PLAYER_WAIT = 20.0  # seconds to wait for a video player to start, capped by the deadline
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

# Play SRF (video.js/Pillarbox): keep only the lowest quality level enabled. Works for
# on-demand videos; SRF live TV exposes no quality levels (it then plays at 540p).
SRF_FORCE_LOW = """
() => {
  const v = document.querySelector('video');
  if (v) { v.muted = true; if (v.paused && !v.ended) v.play().catch(() => {}); }
  if (typeof videojs === 'undefined' || !videojs.getPlayers) return null;
  for (const p of Object.values(videojs.getPlayers()).filter(Boolean)) {
    const ql = p.qualityLevels && p.qualityLevels();
    if (!ql || !ql.length) continue;
    let min = 0;
    for (let i = 0; i < ql.length; i++) if ((ql[i].bitrate || 1e12) < (ql[min].bitrate || 1e12)) min = i;
    for (let i = 0; i < ql.length; i++) ql[i].enabled = (i === min);
    return ql[min].height + 'p';
  }
  return null;
}
"""

VIDEO_RESOLUTION = """
() => { const v = document.querySelector('video'); return v && v.videoHeight ? v.videoWidth + 'x' + v.videoHeight : null; }
"""

MEDIA_STATE = """
() => {
  const m = document.querySelector('video, audio');
  if (!m) return 'none';
  if (m.error) return 'error';
  if (m.ended) return 'ended';
  if (m.paused) return 'paused';
  return m.readyState >= 2 ? 'playing' : 'stalled';  // "playing" without data = blocked/buffering
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


def _names_re(names: list[str]) -> re.Pattern | None:
    """Whole accessible name, case-insensitive. Allowed after it: a trailing arrow or dot,
    or a comma plus a screen-reader hint ("Zwecke anzeigen, Öffnet das ...-Dialogfeld")."""
    if not names:
        return None
    return re.compile(r"^\s*(?:" + "|".join(re.escape(n) for n in names) + r")\s*(?:[→›>.]|,.*)?\s*$", re.I)


class BrowserDriver:
    def __init__(self, playwright_device: str, context_options: dict, consent_buttons: list[str],
                 headless: bool = True, consent_settings_buttons: list[str] | None = None):
        self.playwright_device = playwright_device
        self.context_options = dict(context_options or {})
        self.headless = headless
        self.consent_re = _names_re(consent_buttons)
        self.settings_re = _names_re(consent_settings_buttons or [])
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
        # channel="chromium": the full Chromium build in new headless mode instead of the
        # stripped headless shell. Several shops (digitec, galaxus, zalando) reject the shell.
        self._browser = self._pw.chromium.launch(channel="chromium", headless=self.headless, args=LAUNCH_ARGS)
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
        log.info("page %s", self.page.url)
        return host_of(self.page.url)

    def _dismiss_consent(self) -> None:
        """Reject optional cookies. Many banners only offer 'accept' or 'settings' on the
        first level; then open the settings and reject there. Never accepts."""
        if self.consent_re is None:
            return
        rejected = opened = False
        for _ in range(CONSENT_WAIT_MS // CONSENT_POLL_MS):  # poll until a banner shows up
            self.page.wait_for_timeout(CONSENT_POLL_MS)
            rejected = self._click_button(self.consent_re)
            opened = not rejected and self.settings_re is not None and self._click_button(self.settings_re)
            if rejected or opened:
                break
        if rejected:
            log.info("cookie banner rejected on %s", host_of(self.page.url))
        elif opened:
            self.page.wait_for_timeout(1500)
            if self._click_button(self.consent_re):
                log.info("cookie banner rejected via settings on %s", host_of(self.page.url))
            else:
                log.info("cookie settings opened but no reject button on %s", host_of(self.page.url))
        else:
            return
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except self._error_cls:
            pass

    def _click_button(self, name_re: re.Pattern) -> bool:
        for frame in list(self.page.frames):
            try:
                button = frame.get_by_role("button", name=name_re)
                if button.count() and button.first.is_visible():
                    button.first.click(timeout=3000)
                    return True
            except self._error_cls:
                continue
        return False

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
        until = time.monotonic() + min(timeout, PLAYER_WAIT)
        quality = self._poll(YT_FORCE_LOW, until)  # the player appears a few seconds after load
        log.info("YouTube video %s, player quality: %s, resolution: %s",
                 vid, quality or "unknown", self._poll(VIDEO_RESOLUTION, until) or "unknown (not playing)")
        return host

    def play_srf(self, start_url: str, result_index: int, timeout: float) -> str:
        """Open the SRF Play overview, play the n-th on-demand video at the lowest quality."""
        self.open(start_url, timeout)
        try:
            self.page.wait_for_selector('a[href*="urn:srf:video:"]', state="attached", timeout=timeout * 1000)
            hrefs = self.page.eval_on_selector_all('a[href*="urn:srf:video:"]', "els => els.map(e => e.href)")
        except self._error_cls as e:
            raise PageError(f"no SRF videos found: {str(e).splitlines()[0]}") from None
        videos = [h for h in dict.fromkeys(hrefs) if "/video/" in h]  # DOM order, no live channels
        if not videos:
            raise PageError("no SRF on-demand videos found")
        host = self.open(videos[min(result_index, len(videos) - 1)], timeout)
        until = time.monotonic() + min(timeout, PLAYER_WAIT)
        quality = self._poll(SRF_FORCE_LOW, until)  # quality levels appear a few seconds after load
        log.info("SRF video %s, quality level: %s, resolution: %s",
                 self.page.url, quality or "unknown", self._poll(VIDEO_RESOLUTION, until) or "unknown (not playing)")
        return host

    def _poll(self, script: str, until: float, every_ms: int = 1000):
        """Evaluate `script` until it returns something truthy or the monotonic time `until`."""
        while True:
            try:
                value = self.page.evaluate(script)
            except self._error_cls:
                value = None
            if value or time.monotonic() >= until:
                return value
            self.page.wait_for_timeout(every_ms)

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
            site = site_of(host_of(self.page.url))
            if site == "youtube.com":
                self.page.evaluate(YT_FORCE_LOW)  # quality can reset after ads
            elif site == "srf.ch":
                self.page.evaluate(SRF_FORCE_LOW)
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
