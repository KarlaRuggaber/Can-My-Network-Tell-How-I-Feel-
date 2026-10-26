"""Step limits (runner/steps.py): the guard, a hanging page in a real activity, the process tree."""

import random
import signal
import subprocess
import time
from pathlib import Path

import pytest

from runner import context, steps
from runner.activities import ACTIVITIES
from runner.config import load_mixes, parse_mix
from runner.context import RunContext, StepTimeout
from runner.fake import FakeClock, FakeDriver


@pytest.fixture
def guard():
    previous = signal.getsignal(signal.SIGALRM)
    g = steps.Guard(None)
    g.install()
    yield g
    g.disarm()
    signal.signal(signal.SIGALRM, previous)


def test_step_limit_raises_step_timeout(guard):
    t = time.monotonic()
    with pytest.raises(StepTimeout, match="slow step"):
        with guard.limit(0.2, "slow step"):
            time.sleep(3)
    assert time.monotonic() - t < 1.5


def test_watchdog_wins_over_a_longer_step_limit(guard):
    guard.deadline = time.monotonic() + 0.2
    with pytest.raises(steps.Aborted, match="watchdog"):
        with guard.limit(5, "long step"):
            time.sleep(3)


def test_watchdog_is_armed_again_after_a_step(guard):
    guard.deadline = time.monotonic() + 5
    with guard.limit(1, "quick step"):
        pass
    remaining, _ = signal.getitimer(signal.ITIMER_REAL)
    assert 4 < remaining <= 5


# --- a feed page that hangs (like Reddit stuck in its JS challenge on 25.10) ---------------------

class HangingRedditDriver(FakeDriver):
    """Fake browser on a fake clock, but scrolling a Reddit page blocks for real, like a page with
    a busy main thread. recover() is what the real driver does: drop the hung browser."""

    def scroll_feed(self, seconds, rng):
        if self.url and "reddit.com" in self.url:
            time.sleep(30)  # interrupted by the step limit
        return super().scroll_feed(seconds, rng)


def run_social_passive(seed, monkeypatch, duration=3600):
    monkeypatch.setattr(RunContext, "_limit", lambda self, expected: 0.2)
    monkeypatch.setattr(context, "RECOVER_LIMIT", 1.0)
    previous = signal.getsignal(signal.SIGALRM)
    g = steps.Guard(None)
    g.install()
    try:
        clock = FakeClock()
        driver = HangingRedditDriver(clock)
        ctx = RunContext(driver, clock, duration)
        ctx.mixes = load_mixes()
        ctx.guard = g
        mix = parse_mix("social_passive", ctx.mixes)
        ACTIVITIES["social_passive"].run(ctx, random.Random(f"{seed}/sp"), duration, mix)
    finally:
        g.disarm()
        signal.signal(signal.SIGALRM, previous)
    return driver.calls, ctx


def test_hanging_feed_restarts_the_browser_and_moves_to_another_site(monkeypatch):
    # Find a seed whose block visits Reddit (the mix has Reddit and TikTok without login).
    for seed in range(30):
        calls, ctx = run_social_passive(seed, monkeypatch)
        opened = [c[1] for c in calls if c[0] == "open"]
        if any("reddit.com" in u for u in opened):
            break
    else:
        pytest.skip("no seed opened Reddit")
    recover_at = calls.index(("recover",))
    after = [c[1] for c in calls[recover_at:] if c[0] == "open"]
    assert calls.count(("recover",)) == 1  # one hang, one browser restart
    assert ctx.hung_sites == {"reddit.com"}
    assert after and not any("reddit.com" in u for u in after)  # the rest of the block avoids Reddit
    assert ctx.remaining() == 0  # the block ran to its end instead of failing
    assert ctx.page_errors >= 1


def test_without_hangs_the_draws_are_unchanged():
    mix = parse_mix("social_passive", load_mixes())
    a, b = random.Random(7), random.Random(7)
    assert [mix.pick(a).host for _ in range(50)] == [mix.pick(b, frozenset()).host for _ in range(50)]


def test_avoid_skips_hung_sites_while_others_exist():
    mix = parse_mix("social_passive", load_mixes())
    rng = random.Random(3)
    hosts = {mix.pick(rng, {"reddit.com"}).host for _ in range(200)}
    assert hosts and all(not h.endswith("reddit.com") for h in hosts)
    only = {s.host.split(".")[-2] + "." + s.host.split(".")[-1] for s in mix.all_sites()}
    assert mix.pick(random.Random(1), only).host  # all hung: still returns a site


# --- process tree (Linux /proc; the containers run it, macOS skips) ------------------------------

needs_proc = pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="needs /proc (Linux)")


@needs_proc
def test_kill_descendants_ends_children_and_grandchildren():
    child = subprocess.Popen(["sh", "-c", "sleep 300 & sleep 300"])
    time.sleep(0.3)
    ours = [p for p in steps.descendants() if p == child.pid or p in steps.descendants(child.pid)]
    assert child.pid in ours and len(ours) >= 2  # the shell and its background sleep
    assert steps.kill_descendants(child.pid) >= 1 and steps.kill_descendants() >= 1
    child.wait(timeout=5)
    time.sleep(0.2)

    def alive(pid):
        try:
            return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
        except OSError:
            return False

    assert not [p for p in ours if alive(p)]
