"""Exclusion rule tests."""
from __future__ import annotations

from insta_pipeline.domain.services.exclusions import build_rules


def test_username_denylist():
    r = build_rules(excluded_usernames=["Spammer", "Bob"])
    assert r.excludes_username("spammer")
    assert r.excludes_username("BOB")
    assert not r.excludes_username("alice")


def test_default_substrings_catch_obvious_bots():
    r = build_rules()
    assert r.excludes_username("free_giveaway_promo")
    assert r.excludes_username("buyfollowers123")
    assert not r.excludes_username("real_creator")


def test_custom_substring_and_regex():
    r = build_rules(
        substrings=["news"],
        regexes=[r"^\d+$"],
        use_defaults=False,
    )
    assert r.excludes_username("daily_news")
    assert r.excludes_username("12345")
    assert not r.excludes_username("creator_one")


def test_bio_substrings():
    r = build_rules(bio_substrings=["press inquiries only"], use_defaults=False)
    assert r.excludes_profile("alice", biography="Press inquiries only")
    assert not r.excludes_profile("alice", biography="Hello world")


def test_follower_bounds():
    r = build_rules(min_followers=1000, max_followers=100000, use_defaults=False)
    assert r.excludes_profile("a", follower_count=500)
    assert r.excludes_profile("a", follower_count=200000)
    assert not r.excludes_profile("a", follower_count=5000)


def test_require_posts_excludes_zero_media():
    r = build_rules(use_defaults=False)
    assert r.excludes_profile("a", media_count=0)
    assert not r.excludes_profile("a", media_count=5)


def test_disabling_defaults():
    r = build_rules(use_defaults=False)
    assert not r.excludes_username("free_giveaway")
