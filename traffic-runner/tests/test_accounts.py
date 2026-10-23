"""messaging (Slack) and social_post (Reddit) without network: fake driver, fake sessions."""

import json
import random

import pytest

from runner import sessions
from runner.activities import ACTIVITIES
from runner.browser import reddit_target_ok
from runner.config import load_accounts, load_mixes
from runner.context import NotImplementedActivity, PageError, RunContext
from runner.fake import FakeClock, FakeDriver


def run(activity, duration, seed=1, meta=None):
    clock = FakeClock()
    driver = FakeDriver(clock)
    ctx = RunContext(driver, clock, duration)
    ctx.mixes = load_mixes()
    ctx.accounts = load_accounts()
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
def test_social_post_only_to_configured_subreddit(seed):
    calls, visited, end = run("social_post", 300, seed)
    posts = [c for c in calls if c[0] == "reddit_post"]
    assert len(posts) == 1
    _, subreddit, title, size = posts[0]
    assert subreddit == "CMNTHIF"
    assert 1_000_000 * 0.95 <= size <= 3_000_000 * 1.05
    assert visited == ["www.reddit.com"]


@pytest.mark.parametrize("url, page, ok", [
    ("https://www.reddit.com/r/CMNTHIF/submit/?type=IMAGE", "submit", True),
    ("https://www.reddit.com/r/cmnthif/submit", "submit", True),
    ("https://www.reddit.com/r/CMNTHIF/comments/abc/test_upload/", "comments", True),
    ("https://www.reddit.com/r/CMNTHIF2/submit", "submit", False),       # lookalike subreddit
    ("https://www.reddit.com/r/AskReddit/submit", "submit", False),
    ("https://www.reddit.com/submit", "submit", False),                  # no subreddit chosen
    ("https://www.reddit.com/user/CMNTHIF/submit", "submit", False),     # profile, public
    ("https://evil.example/r/CMNTHIF/submit", "submit", False),
    ("https://www.reddit.com/r/CMNTHIF/comments/abc/", "submit", False),
])
def test_reddit_target_check(url, page, ok):
    assert reddit_target_ok(url, "CMNTHIF", page) is ok


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
    assert acc["reddit"]["subreddit"] == "CMNTHIF"
    assert set(acc["personas"]) == {"gw_student_a", "gw_insomnia_a", "gw_mdd_suicidality_a", "gw_social_anxiety_a"}
