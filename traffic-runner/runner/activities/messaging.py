"""messaging: send 3-10 text messages via a web client, 10-60 s apart, to a scripted
counterpart that replies (catalog §2).

Platform (decided 23.10, email-only accounts): Slack web in the project's own workspace
(slack.com = SOCIAL list). The persona's member account writes to the bot "CMNTHIF Partner"
(peer-vm/slackbot), which answers each message after 5-40 s: real turn-taking. The login
comes from the device's session file (runner/sessions.py).

Slack refuses phone browsers (redirect to the app download), so this activity always uses
a desktop browser profile, also on phone devices. The device keeps its own IP; the capture
only sees TLS to slack.com, where the user agent is not visible.
"""

from ..context import PageError

ID = "messaging"
IMPLEMENTED = True
ROLES = ("phone",)
DEFAULT_DURATION = (120, 600)
NEEDS_MIX = False
DEFAULT_MIX = None
MIX_KIND = None
NEEDS_BROWSER = True
SESSION_PLATFORM = "slack"
PLAYWRIGHT_DEVICE = "Desktop Chrome"

MESSAGES = (3, 10)
GAP = (10, 60)
OPENERS = ["hey", "hi", "kurze frage", "übrigens", "ok", "haha", "sorry", "du"]
TOPICS = ["wie gehts?", "hast du zeit morgen?", "hast du die folien gesehen?", "bin gleich da",
          "was machst du heute abend?", "danke dir!", "lass uns später telefonieren",
          "hab den bus verpasst", "gute idee", "schick mir das bitte nochmal"]


def run(ctx, rng, duration, mix):
    n = rng.randint(*MESSAGES)
    plan = [(f"{rng.choice(OPENERS)} {rng.choice(TOPICS)}", rng.uniform(*GAP)) for _ in range(n)]
    url = ctx.session_meta.get("dm_url")
    if not url:
        raise PageError("Slack session has no dm_url: capture it again with scripts/capture_session.py")
    host = ctx.open(url)
    if host != "app.slack.com":
        raise PageError(f"Slack session expired or invalid (landed on {host}): capture it again")
    for text, gap in plan:
        if ctx.remaining() <= 0:
            break
        ctx.send_message(text)
        ctx.idle(gap)  # the bot's reply arrives while the page stays open
    return ctx.visited
