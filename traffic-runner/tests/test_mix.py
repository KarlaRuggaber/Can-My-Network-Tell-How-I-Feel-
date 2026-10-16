"""mixes.yaml loading and --mix parsing."""

import random

import pytest

from runner.config import ConfigError, MixUnavailable, load_mixes, parse_mix


@pytest.fixture(scope="module")
def mixes():
    return load_mixes()


def test_catalog_categories_present(mixes):
    for cat in ("messaging", "social_passive", "streaming", "news", "work", "study",
                "search", "shopping", "gaming", "crisis_help"):
        assert cat in mixes.categories


def test_equal_and_weighted(mixes):
    assert parse_mix("news,shopping", mixes).weights == (("news", 1.0), ("shopping", 1.0))
    assert parse_mix("news:.2, shopping:.8", mixes).weights == (("news", 0.2), ("shopping", 0.8))


def test_login_sites_are_skipped(mixes):
    mix = parse_mix("social_passive", mixes)
    assert "instagram.com" not in {s.host for s in mix.all_sites()}
    mix = parse_mix("messaging:.4,social_passive:.4,news:.2", mixes)
    assert mix.skipped == ("messaging",)
    assert mix.categories == ["social_passive", "news"]


def test_only_login_categories(mixes):
    with pytest.raises(MixUnavailable):
        parse_mix("messaging", mixes)


def test_video_kind_only_playable(mixes):
    hosts = {s.host for s in parse_mix("streaming", mixes, kind="video").all_sites()}
    assert hosts == {"youtube.com", "play.srf.ch"}  # spotify/netflix need a login


@pytest.mark.parametrize("spec", ["nonsense", "news:abc", "news:0", "news,news", ""])
def test_bad_specs(mixes, spec):
    with pytest.raises(ConfigError):
        parse_mix(spec, mixes)


def test_pick_respects_weights(mixes):
    mix = parse_mix("news:9,shopping:1", mixes)
    rng = random.Random(1)
    cats = [mix.pick(rng).category for _ in range(2000)]
    assert 0.85 < cats.count("news") / len(cats) < 0.95


def test_query_urls(mixes):
    site = parse_mix("search", mixes).all_sites()[0]
    url = site.resolve_url(random.Random(3))
    assert url.startswith("https://duckduckgo.com/?q=") and "{query}" not in url
