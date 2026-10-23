"""Same seed -> same page sequence, without network (fake driver + fake clock)."""

import random

import pytest

from runner.activities import ACTIVITIES
from runner.config import load_mixes, parse_mix
from runner.context import RunContext
from runner.fake import FakeClock, FakeDriver

CASES = [
    ("phone_check", "news,social_passive", 300),
    ("browse", "news:.5,shopping:.3,search:.2", 1800),
    ("repeat_visit_loop", "news,search", 1200),
    ("video_stream", "streaming", 3600),
    ("music_background", None, 1800),
    ("idle_connected", None, 600),
    ("social_passive", "social_passive", 1800),
    ("work_block", "work", 3600),
    ("study_block", "study", 3600),
    ("crisis_resource_visit", "crisis_help", 600),
    ("sh_adjacent_lookup", None, 30),
]


def run_once(activity_id, mix_spec, duration, seed, block_id="b001", overrides=None):
    mixes = load_mixes()
    module = ACTIVITIES[activity_id]
    mix = parse_mix(mix_spec, mixes, kind=module.MIX_KIND) if mix_spec else None
    clock = FakeClock()
    driver = FakeDriver(clock)
    ctx = RunContext(driver, clock, duration, overrides)
    ctx.mixes = mixes
    visited = module.run(ctx, random.Random(f"{seed}/{block_id}"), duration, mix)
    return driver.calls, visited, clock.now()


@pytest.mark.parametrize("activity_id, mix_spec, duration", CASES)
def test_same_seed_same_sequence(activity_id, mix_spec, duration):
    a = run_once(activity_id, mix_spec, duration, seed=42)
    b = run_once(activity_id, mix_spec, duration, seed=42)
    assert a == b


@pytest.mark.parametrize("activity_id, mix_spec, duration", [c for c in CASES if c[0] in
                         ("phone_check", "browse", "repeat_visit_loop", "video_stream", "social_passive",
                          "work_block", "study_block", "crisis_resource_visit", "sh_adjacent_lookup")])
def test_different_seeds_differ(activity_id, mix_spec, duration):
    runs = {repr(run_once(activity_id, mix_spec, duration, seed=s)[0]) for s in range(1, 9)}
    assert len(runs) > 1


def test_block_id_changes_sequence():
    a = run_once("browse", "news,shopping", 1800, seed=42, block_id="b001")[0]
    b = run_once("browse", "news,shopping", 1800, seed=42, block_id="b002")[0]
    assert a != b


@pytest.mark.parametrize("activity_id, mix_spec, duration", CASES)
def test_respects_duration(activity_id, mix_spec, duration):
    for seed in range(5):
        _, _, end = run_once(activity_id, mix_spec, duration, seed=seed)
        assert end <= duration + 1e-6


@pytest.mark.parametrize("seed", range(20))
def test_phone_check_fills_duration_without_pages(seed):
    # catalog §2: without `pages`, keep opening pages until the duration is used up
    calls, visited, end = run_once("phone_check", "news", 900, seed=seed)
    opens = [c for c in calls if c[0] == "open"]
    dwells = [c[1] for c in calls if c[0] == "dwell"][:-1]  # the last one is cut by the deadline
    assert end == pytest.approx(900)
    assert len(opens) >= 900 // (90 + 2)  # at least as many pages as max dwell + load allow
    assert all(20 <= d <= 90 for d in dwells)
    assert len(visited) <= len(opens)


@pytest.mark.parametrize("seed", range(10))
def test_phone_check_default_duration_gives_few_pages(seed):
    calls, _, _ = run_once("phone_check", "news", 120, seed=seed)
    assert 1 <= len([c for c in calls if c[0] == "open"]) <= 6


def test_phone_check_pages_ends_early():
    # catalog §2: with `pages`, open exactly that many and end, even before the duration
    calls, _, end = run_once("phone_check", "news", 3600, seed=1, overrides={"pages": (5, 5), "dwell": (10, 11)})
    assert len([c for c in calls if c[0] == "open"]) == 5
    assert all(10 <= c[1] <= 11 for c in calls if c[0] == "dwell")
    assert end < 100


def test_phone_check_pages_capped_by_duration():
    calls, _, end = run_once("phone_check", "news", 60, seed=1, overrides={"pages": (10, 10)})
    assert len([c for c in calls if c[0] == "open"]) < 10
    assert end <= 60


def test_browse_ranges():
    calls, _, _ = run_once("browse", "news", 7200, seed=3)
    dwells = [c[1] for c in calls if c[0] == "dwell"][:-1]  # the last one is cut by the deadline
    assert dwells and all(30 <= d <= 180 for d in dwells)
    assert any(c[0] == "follow" for c in calls)


def test_repeat_visit_loop_fresh_context_and_interval():
    calls, visited, _ = run_once("repeat_visit_loop", "news", 1800, seed=5)
    assert len(visited) <= 3
    opens = [i for i, c in enumerate(calls) if c[0] == "open"]
    assert all(calls[i - 1] == ("new_context",) for i in opens)  # fresh DNS cache before every visit
    # visit + idle = 60-180 s; the fake load takes 2 s
    idles = [c[1] for c in calls if c[0] == "idle"][:-1]  # last one is cut by the deadline
    assert all(58 <= i <= 178 for i in idles)


def test_video_stream_ends_early_when_media_ends():
    mixes = load_mixes()
    clock = FakeClock()
    driver = FakeDriver(clock, media_length=200)
    ctx = RunContext(driver, clock, 3600)
    ctx.mixes = mixes
    ACTIVITIES["video_stream"].run(ctx, random.Random("1/b1"), 3600, parse_mix("streaming", mixes, kind="video"))
    assert 200 <= clock.now() < 230


@pytest.mark.parametrize("state", ["stalled", "paused", "none", "error"])
def test_media_that_does_not_play_fails(state):
    from runner.context import PageError

    class StuckDriver(FakeDriver):
        def media_state(self):
            return state

    mixes = load_mixes()
    clock = FakeClock()
    ctx = RunContext(StuckDriver(clock), clock, 600)
    ctx.mixes = mixes
    with pytest.raises(PageError):
        ACTIVITIES["video_stream"].run(ctx, random.Random("1/b1"), 600, parse_mix("streaming", mixes, kind="video"))
    assert clock.now() < 60  # fails after three checks, not at the end of the block


def test_music_background_uses_radio_page():
    calls, visited, end = run_once("music_background", None, 600, seed=3)
    assert calls[0][0] == "audio_page" and calls[0][1].startswith("https://www.srf.ch/audio/")
    assert visited == ["www.srf.ch"]
    assert end == pytest.approx(600)


@pytest.mark.parametrize("seed", range(10))
def test_social_passive_feed_and_videos(seed):
    calls, _, end = run_once("social_passive", "social_passive,news", 3600, seed=seed)
    assert end == pytest.approx(3600)
    feeds = [c for c in calls if c[0] == "feed"]
    assert feeds and all(c[2] >= 1 for c in feeds)
    assert len([c for c in calls if c[0] == "follow"]) <= 2  # catalog: 0-2 videos
    assert len([c for c in calls if c[0] == "open"]) >= 2  # 1 h switches sites (3-10 min segments)


def test_work_block_refreshes_home_and_opens_pages():
    calls, _, end = run_once("work_block", "work", 7200, seed=4)
    opens = [c[1] for c in calls if c[0] == "open"]
    home = opens[0]
    assert end == pytest.approx(7200)
    assert opens.count(home) >= 7200 // 300  # reloaded at least every 5 min
    assert not [c for c in calls if c[0] == "download"]


def test_study_block_downloads_pdfs():
    downloads = 0
    for seed in range(10):
        calls, visited, _ = run_once("study_block", "study", 7200, seed=seed)
        downloads += len([c for c in calls if c[0] == "download"])
    assert 10 <= downloads <= 70  # 1-3 per hour on average, 2 h x 10 runs


@pytest.mark.parametrize("seed", range(10))
def test_crisis_resource_visit(seed):
    calls, visited, end = run_once("crisis_resource_visit", "crisis_help", 600, seed=seed)
    opens = [c for c in calls if c[0] == "open"]
    dwells = [c[1] for c in calls if c[0] == "dwell"]
    assert 1 <= len(opens) <= 3
    assert all(o[1].split("/")[2].endswith(("143.ch", "147.ch", "depression.ch")) for o in opens)
    assert all(60 <= d <= 240 for d in dwells[:-1])
    assert end <= 600


@pytest.mark.parametrize("seed", range(10))
def test_sh_adjacent_lookup_placeholders_only(seed):
    calls, visited, _ = run_once("sh_adjacent_lookup", None, 30, seed=seed)
    names = [c[1] for c in calls if c[0] == "dns"]
    assert 1 <= len(names) <= 3
    assert all(n.startswith("sh-adjacent-") and n.endswith(".invalid") for n in names)
    assert visited == list(dict.fromkeys(names))
    assert not [c for c in calls if c[0] == "open"]


def test_sh_adjacent_lookup_override():
    calls, _, _ = run_once("sh_adjacent_lookup", None, 60, seed=1, overrides={"lookups": (3, 3)})
    assert len([c for c in calls if c[0] == "dns"]) == 3


@pytest.fixture
def peer_vm(monkeypatch):
    from runner import peer
    joins = []
    monkeypatch.setenv("RUNNER_PEER_URL", "https://peer.test")
    monkeypatch.setenv("RUNNER_PEER_TOKEN", "secret")
    monkeypatch.setattr(peer.Peer, "request_join", lambda self, room, duration, video: joins.append((room, duration, video)))
    return joins


def run_with_key(activity_id, mix_spec, duration, seed, run_key):
    mixes = load_mixes()
    module = ACTIVITIES[activity_id]
    mix = parse_mix(mix_spec, mixes) if mix_spec else None
    clock = FakeClock()
    driver = FakeDriver(clock)
    ctx = RunContext(driver, clock, duration)
    ctx.mixes = mixes
    ctx.run_key = run_key
    module.run(ctx, random.Random(f"{seed}/b1"), duration, mix)
    return driver.calls, ctx.visited, clock.now()


@pytest.mark.parametrize("activity_id, video", [("video_call", True), ("voice_call", False)])
def test_calls_ask_peer_then_join_same_room(peer_vm, activity_id, video):
    calls, visited, end = run_with_key(activity_id, None, 1800, 1, "student/42/b1")
    room, duration, asked_video = peer_vm[0]
    assert (duration, asked_video) == (1800, video)
    assert calls[0] == ("call", f"https://peer.test/{room}")
    assert visited == ["peer.test"] and end == pytest.approx(1800)


def test_call_room_is_per_run_and_secret(peer_vm):
    from runner.peer import Peer
    p = Peer("https://peer.test", "secret")
    assert p.room_for("student/42/b1") == p.room_for("student/42/b1")
    assert p.room_for("student/42/b1") != p.room_for("student/42/b2")
    assert p.room_for("student/42/b1") != Peer("https://peer.test", "other").room_for("student/42/b1")
    assert "startWithVideoMuted=true" in p.call_url("r-x", video=False, name="runner")


@pytest.mark.parametrize("seed", range(5))
def test_gaming_session_store_then_game(peer_vm, seed):
    calls, visited, end = run_with_key("gaming_session", "gaming", 3600, seed, "student/42/g1")
    game = [i for i, c in enumerate(calls) if c[0] == "game"]
    assert len(game) == 1
    store = [c[1] for c in calls[:game[0]] if c[0] == "open"]
    assert store and all("steampowered" in u or "riotgames" in u for u in store)
    tick = int(calls[game[0]][1].split("tick=")[1].split("&")[0])
    assert 20 <= tick <= 60
    assert end == pytest.approx(3600)
    assert not peer_vm  # gaming does not ask the peer to join anything


def test_gaming_session_same_seed_same_plan(peer_vm):
    a = run_with_key("gaming_session", "gaming", 3600, 3, "k")
    b = run_with_key("gaming_session", "gaming", 3600, 3, "k")
    assert a == b
