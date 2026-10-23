"""Reply bot "CMNTHIF Partner" for the runner's messaging activity (catalog §2: the
counterpart account is scripted too, so there is real turn-taking).

Official Slack app in the project's own workspace, connected outbound via Socket Mode (no
public address needed). It answers every direct message of a member after 5-40 s with a short
reply. Tokens come from the environment (peer-vm/.env, root-only):
    SLACK_APP_TOKEN  xapp-…  (Socket Mode, scope connections:write)
    SLACK_BOT_TOKEN  xoxb-…  (chat:write, im:history, im:read, users:read)
Without tokens it logs a warning and idles instead of restarting in a loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random

from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web.async_client import AsyncWebClient

DELAY = (5.0, 40.0)
REPLIES = ["ja klar", "gut und dir?", "morgen geht", "haha ok", "danke!", "bin unterwegs, später",
           "hab ich gesehen", "ok passt", "klingt gut", "ich meld mich", "👍", "sorry, war beschäftigt"]

log = logging.getLogger("slackbot")


async def reply(web: AsyncWebClient, channel: str) -> None:
    await asyncio.sleep(random.uniform(*DELAY))
    try:
        await web.chat_postMessage(channel=channel, text=random.choice(REPLIES))
    except Exception as e:  # noqa: BLE001 - one failed reply must not stop the bot
        log.warning("reply to %s failed: %s", channel, e)


async def main() -> None:
    app_token = os.environ.get("SLACK_APP_TOKEN", "")
    bot_token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not app_token.startswith("xapp-") or not bot_token.startswith("xoxb-"):
        log.warning("SLACK_APP_TOKEN / SLACK_BOT_TOKEN not set in .env: bot idle")
        await asyncio.Event().wait()
    web = AsyncWebClient(token=bot_token)
    client = SocketModeClient(app_token=app_token, web_client=web)

    async def handle(client: SocketModeClient, req: SocketModeRequest) -> None:
        if req.type != "events_api":
            return
        await client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        event = req.payload.get("event", {})
        if (event.get("type") == "message" and event.get("channel_type") == "im"
                and not event.get("bot_id") and not event.get("subtype")):
            log.info("message from %s, replying", event.get("user"))
            asyncio.create_task(reply(web, event["channel"]))

    client.socket_mode_request_listeners.append(handle)
    await client.connect()
    log.info("connected to Slack (Socket Mode)")
    await asyncio.Event().wait()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())
