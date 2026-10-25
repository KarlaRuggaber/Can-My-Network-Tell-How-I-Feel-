"""messaging (Slack) and social_post (Discord webhook) without network: fake driver, fake sessions."""

import json
import random

import pytest

from runner import sessions
from runner.activities import ACTIVITIES
from runner.config import load_accounts, load_mixes
from runner.context import NotImplementedActivity, PageError, RunContext
from runner.fake import FakeClock, FakeDriver


WEBHOOK_ID, CHANNEL_ID = "123456789012345678", "987654321098765432"
WEBHOOK = f"https://discord.com/api/webhooks/{WEBHOOK_ID}/abcdefghijklmnopqrstuvwxyz0123456789"


def run(activity, duration, seed=1, meta=None, reply_channel=CHANNEL_ID):
    clock = FakeClock()
    driver = FakeDriver(clock)
    driver.webhook_channel_id = reply_channel
    ctx = RunContext(driver, clock, duration)
    ctx.mixes = load_mixes()
    ctx.accounts = {**load_accounts(), "discord": {"webhook_id": WEBHOOK_ID, "channel_id": CHANNEL_ID}}
    ctx.webhook_url = WEBHOOK
    ctx.session_meta = meta if meta is not None else {"dm_url": "https://app.slack.com/client/T1/D1"}
    ACTIVITIES[activity].run(ctx, random.Random(f"{seed}/m1"), duration, None)
    return driver.calls, ctx.visited, clock.now()


@pytest.mark.parametrize("seed", range(10))
def test_messaging_sends_3_to_10_messages(seed):
    calls, visited, end = run("messaging", 3600, seed)
    msgs = [c for c in calls if c[0] == "message"]
    gaps = [c[1] for c in calls if c[0] == "idle"]
    assert calls[0] == ("open", "https://app.slack.com/client/T1/D1")
    assert 3 <= len(msgs) <= 10
    assert all(10 <= g <= 60 for g in gaps)
    assert visited == ["app.slack.com"] and end < 3600  # ends when done (duration = upper bound)


def test_messaging_same_seed_same_messages():
    assert run("messaging", 3600, 5)[0] == run("messaging", 3600, 5)[0]


def test_messaging_refuses_expired_session():
    with pytest.raises(PageError):
        run("messaging", 600, meta={"dm_url": "https://slack.com/signin"})  # landed outside app.slack.com
    with pytest.raises(PageError):
        run("messaging", 600, meta={})


@pytest.mark.parametrize("seed", range(5))
def test_social_post_one_upload_through_the_configured_webhook(seed):
    calls, visited, end = run("social_post", 300, seed)
    posts = [c for c in calls if c[0] == "webhook_post"]
    assert len(posts) == 1
    _, hook, title, size = posts[0]
    assert hook == WEBHOOK_ID
    assert 1_000_000 * 0.95 <= size <= 3_000_000 * 1.05
    opened = [c[1] for c in calls if c[0] == "open"]
    assert opened == [f"https://cdn.discordapp.com/attachments/{CHANNEL_ID}/1/test.png"]  # looks at the post
    assert visited == ["discord.com", "cdn.discordapp.com"]
    assert end <= 300


def test_social_post_refuses_a_message_in_another_channel():
    with pytest.raises(PageError, match="landed in channel"):
        run("social_post", 300, reply_channel="111111111111111111")


def test_social_post_same_seed_same_upload():
    assert run("social_post", 300, 4)[0] == run("social_post", 300, 4)[0]


def test_sessions_load(tmp_path):
    with pytest.raises(NotImplementedActivity):
        sessions.load("student_a_phone", "slack", tmp_path)
    state, meta = sessions.paths("student_a_phone", "slack", tmp_path)
    state.write_text("{}")
    meta.write_text(json.dumps({"dm_url": "https://app.slack.com/client/T1/D1"}))
    path, m = sessions.load("student_a_phone", "slack", tmp_path)
    assert path == state and m["dm_url"].endswith("/D1")


def test_accounts_config():
    acc = load_accounts()
    assert acc["discord"]["server"] == "CMNTHIF" and "reddit" not in acc
    assert set(acc["personas"]) == {"gw_student_a", "gw_insomnia_a", "gw_mdd_suicidality_a", "gw_social_anxiety_a"}
