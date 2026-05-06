"""Unit tests for pure domain services. Run: python -m pytest tests/ -v"""
from __future__ import annotations
import datetime as dt
import json
import os
import tempfile

import pytest

from insta_pipeline.domain.models import RawCreatorData
from insta_pipeline.domain.services.analyzer import analyze
from insta_pipeline.domain.services.basic_info import extract_basic_info
from insta_pipeline.domain.services.contact import extract_email, extract_phone
from insta_pipeline.domain.services.creator_size import determine_creator_size
from insta_pipeline.domain.services.gender import identify_gender
from insta_pipeline.domain.services.hashtags import extract_hashtags_and_mentions
from insta_pipeline.domain.services.locations import (
    extract_location_from_posts, parse_address,
)
from insta_pipeline.domain.services.names import extract_names
from insta_pipeline.domain.services.niche import identify_niche
from insta_pipeline.domain.services.pricing import extract_creator_pricing
from insta_pipeline.domain.services.social_links import extract_social_links
from insta_pipeline.domain.services.collaborations import (
    identify_collaborations, extract_ugc_examples,
)
from insta_pipeline.domain.services.engagement import calculate_top_post_er
from insta_pipeline.adapters.exporters.streaming_csv_exporter import (
    StreamingCsvExporter,
)
from insta_pipeline.adapters.name_providers.ssa_name_provider import (
    SSAFirstNameValidator, PassthroughFirstNameValidator,
)


def _now_ts(days_ago: int = 0) -> int:
    return int((dt.datetime.now() - dt.timedelta(days=days_ago)).timestamp())


@pytest.fixture
def sample_user():
    return {
        "data": {
            "user": {
                "id": "123", "account_type": 2,
                "username": "jane_doe", "full_name": "Jane Doe",
                "biography": "Fitness coach 💪 #yoga jane@example.com +1 555-123-4567",
                "follower_count": 75000, "following_count": 300, "media_count": 200,
                "category": "Health/Beauty",
                "is_business": True, "is_private": False, "is_verified": True,
                "external_url": "https://janedoe.com",
                "address_street": "1 Main St", "city_name": "Austin", "zip": "78701",
                "pronouns": [{"pronoun": "she/her"}],
                "bio_links": [
                    {"url": "https://tiktok.com/@jane"},
                    {"url": "https://youtube.com/@jane"},
                ],
            }
        }
    }


@pytest.fixture
def sample_posts():
    return {
        "data": {
            "xdt_api__v1__feed__user_timeline_graphql_connection": {
                "edges": [
                    {"node": {
                        "id": "1", "code": "AAA",
                        "taken_at": _now_ts(5),
                        "like_count": 1000, "comment_count": 50,
                        "product_type": "clips",
                        "is_paid_partnership": True,
                        "caption": {"text": "loving @nike #ad amazing"},
                        "user": {"username": "jane_doe"},
                        "owner": {"username": "jane_doe"},
                        "location": {
                            "name": "Austin, TX", "lat": 30.26, "lng": -97.74,
                            "address": "Austin, TX, USA", "city": "Austin",
                        },
                    }},
                    {"node": {
                        "id": "2", "code": "BBB", "taken_at": _now_ts(15),
                        "like_count": 500, "comment_count": 20,
                        "caption": {"text": "yoga workout #fitness"},
                        "user": {"username": "jane_doe"},
                        "owner": {"username": "jane_doe"},
                    }},
                ]
            }
        }
    }


def test_basic_info(sample_user):
    info = extract_basic_info(sample_user)
    assert info["username"] == "jane_doe"
    assert info["follower_count"] == 75000
    assert info["is_verified"] is True
    assert info["profile_picture"].endswith("jane_doe.jpg")


def test_gender(sample_user):
    assert identify_gender(sample_user) == "Female"


def test_social_links(sample_user):
    s = extract_social_links(sample_user)
    assert "tiktok.com" in s["tiktok"]
    assert "youtube.com" in s["youtube"]
    assert s["x"] is None


def test_email_phone(sample_user):
    assert extract_email(sample_user) == "jane@example.com"
    phone = extract_phone(sample_user)
    assert phone and "5551234567" in phone


def test_names(sample_user):
    f, l = extract_names(sample_user)
    assert f == "Jane" and l == "Doe"


def test_creator_size(sample_user):
    assert determine_creator_size(sample_user) == "Mid-Tier Influencer"


def test_niche(sample_user, sample_posts):
    posts = sample_posts["data"]["xdt_api__v1__feed__user_timeline_graphql_connection"]["edges"]
    n = identify_niche(sample_user, posts)
    assert n["overall_niche"] == "Fitness & Wellness"
    assert n["confidence_level"] in {"Low", "Medium", "High"}


def test_collaborations_and_ugc(sample_posts):
    posts = sample_posts["data"]["xdt_api__v1__feed__user_timeline_graphql_connection"]["edges"]
    c = identify_collaborations(posts)
    assert c["status"] == "Active"
    assert c["total_collaborations"] >= 1
    assert any(x["name"] == "nike" for x in c["all_collaborations"])
    ugc = extract_ugc_examples(posts)
    assert "instagram.com/p/AAA" in ugc


def test_engagement(sample_user, sample_posts):
    total, top, avg = calculate_top_post_er(sample_user, sample_posts)
    assert total == 2
    assert len(top) == 2
    assert avg > 0


def test_hashtags_mentions(sample_posts):
    posts = sample_posts["data"]["xdt_api__v1__feed__user_timeline_graphql_connection"]["edges"]
    h = extract_hashtags_and_mentions(posts, limit=5)
    assert "fitness" in h["hashtags"] or "ad" in h["hashtags"]
    assert h["total_posts_analyzed"] == 2


def test_locations(sample_posts):
    posts = sample_posts["data"]["xdt_api__v1__feed__user_timeline_graphql_connection"]["edges"]
    loc = extract_location_from_posts(posts)
    assert loc["primary_location"] == "Austin, TX"
    assert loc["primary_lat"] == 30.26
    addr = parse_address("Austin, TX", "Austin, TX, USA", "Austin")
    assert addr["country"] == "USA"
    assert addr["state"] == "Texas"
    assert addr["city"] == "Austin"


def test_pricing_tiers(sample_user, sample_posts):
    posts = sample_posts["data"]["xdt_api__v1__feed__user_timeline_graphql_connection"]["edges"]
    p = extract_creator_pricing(sample_user, posts)
    assert p["creator_type"] == "Social Media Influencer"
    assert p["tier"] == "Macro"
    pm = p["creator_pricing_metrics"]
    assert pm["time_15_seconds"] == 2500
    assert pm["time_greater_than_5_minutes"] == 10000
    assert pm["impressions_visibility"] == "1M"


def test_pricing_ugc_beginner():
    user = {"data": {"user": {"username": "x", "full_name": "X", "biography": "small",
                              "follower_count": 200}}}
    p = extract_creator_pricing(user, [])
    assert p["creator_type"] == "UGC Creator"
    assert p["tier"] == "Beginner"


def test_full_analyze(sample_user, sample_posts):
    raw = RawCreatorData(user_info=sample_user, post_info=sample_posts,
                         scraped_timestamp=_now_ts(0))
    res = analyze(raw)
    assert res is not None
    d = res.as_dict()
    assert d["username"] == "jane_doe"
    assert d["gender"] == "Female"
    assert d["niche_data"]["overall_niche"] == "Fitness & Wellness"
    assert d["creator_size"] == "Mid-Tier Influencer"
    assert d["primary_location_name"] == "Austin, TX"
    assert d["address_country"] == "USA"
    assert d["collaboration_status"] == "Active"
    assert d["tier"] == "Macro"


def test_analyze_returns_none_on_empty():
    raw = RawCreatorData(user_info={}, post_info={})
    assert analyze(raw) is None


def test_ssa_name_validator(tmp_path):
    f = tmp_path / "ssa.txt"
    f.write_text("Jane,F,1\nJohn,M,1\n")
    v = SSAFirstNameValidator(str(f))
    assert v.normalize("jane", "fallback") == "Jane"
    assert v.normalize("Xyzqq", "fallback") == "@fallback"


def test_passthrough_validator():
    v = PassthroughFirstNameValidator()
    assert v.normalize("Bob", "u") == "Bob"
    assert v.normalize("", "u") == "@u"


def test_streaming_csv_exporter(sample_user, sample_posts, tmp_path):
    raw = RawCreatorData(user_info=sample_user, post_info=sample_posts,
                         scraped_timestamp=_now_ts(0))
    res = analyze(raw).as_dict()
    aj = tmp_path / "analyzed.json"
    with open(aj, "w", encoding="utf-8") as f:
        json.dump({"analysis_date": "now", "creators": [res], "total_creators_analyzed": 1}, f)
    csv_path = tmp_path / "out.csv"
    n = StreamingCsvExporter().export(str(aj), str(csv_path))
    assert n == 1
    text = csv_path.read_text(encoding="utf-8")
    assert "jane_doe" in text
    assert "Macro" in text
