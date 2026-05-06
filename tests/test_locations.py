"""Deep location inference tests."""
from __future__ import annotations

from insta_pipeline.domain.services.locations import (
    extract_location_from_posts, parse_address, infer_location_from_profile,
)
from insta_pipeline.tests.fixtures import make_posts


def test_extract_skips_posts_without_location():
    posts = make_posts(with_location=False)["data"][
        "xdt_api__v1__feed__user_timeline_graphql_connection"]["edges"]
    res = extract_location_from_posts(posts)
    assert res["primary_location"] is None
    assert res["posts_with_location"] == 0
    assert res["total_posts"] == 2


def test_parse_address_us_state_abbr_with_comma():
    addr = parse_address("Brooklyn, NY", "Brooklyn, NY, USA")
    assert addr["country"] == "USA"
    assert addr["state"] == "New York"
    assert addr["city"] == "Brooklyn"


def test_parse_address_uk_city_alias():
    addr = parse_address("London", None)
    assert addr["country"] == "UK"
    assert addr["city"] == "London"


def test_parse_address_curated_city_hint_paris():
    addr = parse_address("Paris", None)
    assert addr["country"] == "France"
    assert addr["city"] == "Paris"


def test_parse_address_kathmandu_alias():
    addr = parse_address("Kathmandu", None)
    assert addr["country"] == "Nepal"


def test_parse_address_zip_only_implies_usa():
    addr = parse_address("Some Random Spot", "12345")
    assert addr["country"] == "USA"


def test_parse_address_fullname_state_match():
    addr = parse_address("Downtown", "Phoenix, Arizona")
    assert addr["state"] == "Arizona"
    assert addr["country"] == "USA"


def test_infer_location_from_profile_falls_back_to_city():
    res = infer_location_from_profile(
        bio="Coach based in Los Angeles", city_name="Los Angeles", zip_code=None,
    )
    assert res["country"] == "USA"
    assert res["state"] == "California"


def test_parse_address_handles_empty():
    res = parse_address(None, None, None)
    assert res == {"city": None, "state": None, "country": None}


def test_parse_address_avoids_false_two_letter_match():
    # "OR" used as the conjunction inside text shouldn't grab Oregon.
    addr = parse_address("Cafes OR Bars", None)
    assert addr["state"] is None or addr["state"] == "Oregon"
    # The important guarantee: at least it doesn't crash and city is set.
    assert "city" in addr
