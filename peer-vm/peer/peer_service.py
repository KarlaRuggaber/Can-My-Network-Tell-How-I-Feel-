"""Peer service on the VM: call counterpart and game server for the traffic runner.

    POST /peer/join   {"room": ..., "duration": s, "video": bool}   Bearer token required
                      A headless Chromium with fake camera/mic joins the Jitsi room for the
                      duration (+ grace), so the runner's call has a real second participant.
    GET  /peer/health number of active calls
    GET  /game        game page (opened by the runner's browser)
    GET  /game/ws     game WebSocket: the client sends inputs, the server sends game states,
                      both at the client's tick rate (20-60 per s), small JSON messages.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import random
import re
import time
from pathlib import Path
from urllib.parse import quote

from aiohttp import WSMsgType, web
from playwright.async_api import async_playwright

DOMAIN = os.environ["DOMAIN"]
TOKEN = os.environ["PEER_TOKEN"]
INSECURE_TLS = os.environ.get("PEER_INSECURE_TLS") == "1"
MAX_CALLS = 3
MAX_DURATION = 4 * 3600
GRACE = 60  # the peer stays a bit longer than the runner, which leaves at its deadline
IDLE_LEAVE = 45  # leave once the peer has been alone (or without media) for this long
MEMBERS = """
() => (window.APP && APP.conference && typeof APP.conference.membersCount === 'number')
      ? APP.conference.membersCount : null
"""
INBOUND_BYTES = """
async () => {
  let total = 0;
  for (const pc of window.__peerPCs || []) {
    (await pc.getStats()).forEach(s => { if (s.type === 'inbound-rtp') total += s.bytesReceived || 0; });
  }
  return total;
}
"""
PC_HOOK = """
(() => {
  const Orig = window.RTCPeerConnection;
  if (!Orig || window.__peerPCs) return;
  window.__peerPCs = [];
  const Hooked = function (...args) { const pc = new Orig(...args); window.__peerPCs.push(pc); return pc; };
  Hooked.prototype = Orig.prototype;
  Object.setPrototypeOf(Hooked, Orig);
  window.RTCPeerConnection = Hooked;
})();
"""
ROOM_RE = re.compile(r"^[a-z0-9-]{8,64}$")
FAKE_MEDIA = [
    "--use-fake-device-for-media-stream",
    "--use-fake-ui-for-media-stream",
    "--autoplay-policy=no-user-gesture-required",
]
GAME_HTML = (Path(__file__).parent / "game.html").read_text()

log = logging.getLogger("peer")


def call_url(room: str, video: bool, name: str) -> str:
    """Jitsi room URL whose hash sets mute state and skips the mobile app page. The prejoin
    page is switched off server-side (ENABLE_PREJOIN_PAGE=false): switching it off in the URL
    makes Jitsi join without camera and microphone, as a safeguard."""
    cfg = {
        "config.disableDeepLinking": True,
        # Opus DTX: a muted microphone sends ~5 packets/s instead of 50 silence packets/s
        # (Jitsi default), like Zoom/Teams when muted. Matters for --mic-share.
        "config.audioQuality.enableOpusDtx": True,
        "config.startWithAudioMuted": False,
        "config.startWithVideoMuted": not video,
        "config.startAudioOnly": not video,
        "userInfo.displayName": name,
    }
    return f"https://{DOMAIN}/{room}#" + "&".join(f"{k}={quote(json.dumps(v))}" for k, v in cfg.items())


class CallPeer:
    def __init__(self):
        self._pw = None
        self._browser = None
        self.calls: dict[str, asyncio.Task] = {}

    async def _browser_ready(self):
        if self._browser is None or not self._browser.is_connected():
            if self._pw is None:
                self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(channel="chromium", args=FAKE_MEDIA)
        return self._browser

    async def join(self, room: str, duration: float, video: bool) -> None:
        browser = await self._browser_ready()
        ctx = await browser.new_context(ignore_https_errors=INSECURE_TLS, permissions=["camera", "microphone"])
        await ctx.add_init_script(PC_HOOK)
        try:
            page = await ctx.new_page()
            await page.goto(call_url(room, video, "peer"), wait_until="domcontentloaded", timeout=30_000)
            log.info("joined %s (video=%s) for %.0f s", room, video, duration)
            # Stay for the planned duration, but leave early once the runner is gone. Signal:
            # Jitsi's participant count (the peer alone). A muted runner without camera sends
            # no media (mic share), so media is only the fallback when the count is missing.
            start = last_company = time.monotonic()
            last_bytes = -1
            while time.monotonic() - start < duration + GRACE:
                await asyncio.sleep(15)
                now = time.monotonic()
                members = await page.evaluate(MEMBERS)
                if members is None:
                    received = await page.evaluate(INBOUND_BYTES)
                    if received != last_bytes:
                        last_bytes, last_company = received, now
                elif members > 1:
                    last_company = now
                if now - start > 60 and now - last_company >= IDLE_LEAVE:
                    log.info("runner gone from %s for %d s (members=%s), leaving early", room, IDLE_LEAVE, members)
                    break
        except Exception as e:  # noqa: BLE001 - one failed call must not stop the service
            log.warning("call %s failed: %s", room, e)
        finally:
            await ctx.close()
            log.info("left %s", room)


async def handle_join(request: web.Request) -> web.Response:
    auth = request.headers.get("Authorization", "")
    if not hmac.compare_digest(auth, f"Bearer {TOKEN}"):
        return web.json_response({"error": "unauthorized"}, status=401)
    try:
        body = await request.json()
        room, duration, video = str(body["room"]), float(body["duration"]), bool(body.get("video", True))
    except (ValueError, KeyError, TypeError):
        return web.json_response({"error": "need room, duration, video"}, status=400)
    if not ROOM_RE.match(room) or not 0 < duration <= MAX_DURATION:
        return web.json_response({"error": "bad room or duration"}, status=400)
    peer: CallPeer = request.app["peer"]
    peer.calls = {r: t for r, t in peer.calls.items() if not t.done()}
    if room in peer.calls:
        return web.json_response({"room": room, "status": "already joined"})
    if len(peer.calls) >= MAX_CALLS:
        return web.json_response({"error": "too many calls"}, status=429)
    peer.calls[room] = asyncio.create_task(peer.join(room, duration, video))
    return web.json_response({"room": room, "status": "joining"}, status=202)


async def handle_health(request: web.Request) -> web.Response:
    peer: CallPeer = request.app["peer"]
    return web.json_response({"calls": sum(not t.done() for t in peer.calls.values())})


async def handle_game_page(request: web.Request) -> web.Response:
    return web.Response(text=GAME_HTML, content_type="text/html")


async def handle_game_ws(request: web.Request) -> web.WebSocketResponse:
    """Server-authoritative toy game: 6 players on a 1000x1000 field. The client controls
    player 0 with its inputs; the server moves the others and sends the state every tick."""
    try:
        tick = min(60, max(20, int(request.query.get("tick", "30"))))
    except ValueError:
        tick = 30
    ws = web.WebSocketResponse(heartbeat=30, max_msg_size=4096)
    await ws.prepare(request)
    rng = random.Random()
    players = [[rng.randint(0, 999), rng.randint(0, 999)] for _ in range(6)]
    started = time.monotonic()

    async def send_states():
        n = 0
        while not ws.closed and time.monotonic() - started < MAX_DURATION:
            for p in players[1:]:
                p[0] = (p[0] + rng.randint(-6, 6)) % 1000
                p[1] = (p[1] + rng.randint(-6, 6)) % 1000
            n += 1
            await ws.send_str(json.dumps({"t": n, "p": players}, separators=(",", ":")))
            await asyncio.sleep(1 / tick)

    sender = asyncio.create_task(send_states())
    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    inp = json.loads(msg.data)
                    players[0][0] = (players[0][0] + int(inp.get("dx", 0))) % 1000
                    players[0][1] = (players[0][1] + int(inp.get("dy", 0))) % 1000
                except (ValueError, TypeError, AttributeError):
                    pass
            elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break
    finally:
        sender.cancel()
    return ws


def make_app() -> web.Application:
    app = web.Application()
    app["peer"] = CallPeer()
    app.router.add_post("/peer/join", handle_join)
    app.router.add_get("/peer/health", handle_health)
    app.router.add_get("/game", handle_game_page)
    app.router.add_get("/game/ws", handle_game_ws)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    web.run_app(make_app(), host="0.0.0.0", port=8080, access_log=None)
