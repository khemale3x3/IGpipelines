"""Reusable test fixtures: sample HTML, CSV, and raw scraped JSON."""
from __future__ import annotations
import datetime as dt
from typing import Any, Dict

from ..domain.models import RawCreatorData


def _ts(days_ago: int = 0) -> int:
    return int((dt.datetime.now() - dt.timedelta(days=days_ago)).timestamp())


SAMPLE_PROFILE_HTML = """<!doctype html>
<html lang="en">
  <head>
    <title>jane_doe (@jane_doe) • Instagram photos and videos</title>
    <meta property="og:description"
      content="75K Followers, 300 Following, 200 Posts - Fitness coach \u2728">
  </head>
  <body>
    <header>
      <h2>jane_doe</h2>
      <span class="bio">Fitness coach \u2728 Austin, TX \u2022 jane@example.com</span>
    </header>
  </body>
</html>"""


SAMPLE_INPUT_CSV = (
    "url\n"
    "https://www.instagram.com/jane_doe/\n"
    "https://www.instagram.com/spam_promo_bot/\n"
    "https://www.instagram.com/london_chef/\n"
)


def make_user(
    username: str = "jane_doe",
    full_name: str = "Jane Doe",
    bio: str = "Fitness coach",
    followers: int = 75000,
    media: int = 200,
    city: str | None = "Austin",
    zip_code: str | None = "78701",
) -> Dict[str, Any]:
    return {
        "data": {
            "user": {
                "id": "1",
                "account_type": 2,
                "username": username,
                "full_name": full_name,
                "biography": bio,
                "follower_count": followers,
                "following_count": 300,
                "media_count": media,
                "category": "Health/Beauty",
                "is_business": True, "is_private": False, "is_verified": False,
                "external_url": f"https://{username}.com",
                "address_street": None,
                "city_name": city,
                "zip": zip_code,
                "pronouns": [],
                "bio_links": [],
            }
        }
    }


def make_posts(*, with_location: bool = True) -> Dict[str, Any]:
    edges = [
        {"node": {
            "id": "1", "code": "AAA",
            "taken_at": _ts(5),
            "like_count": 1000, "comment_count": 50,
            "product_type": "clips",
            "is_paid_partnership": True,
            "caption": {"text": "loving @nike #ad amazing yoga"},
            "user": {"username": "jane_doe"},
            "owner": {"username": "jane_doe"},
        }},
        {"node": {
            "id": "2", "code": "BBB",
            "taken_at": _ts(15),
            "like_count": 500, "comment_count": 20,
            "caption": {"text": "yoga workout #fitness"},
            "user": {"username": "jane_doe"},
            "owner": {"username": "jane_doe"},
        }},
    ]
    if with_location:
        edges[0]["node"]["location"] = {
            "name": "Austin, TX", "lat": 30.26, "lng": -97.74,
            "address": "Austin, TX, USA", "city": "Austin",
        }
    return {
        "data": {
            "xdt_api__v1__feed__user_timeline_graphql_connection": {"edges": edges}
        }
    }


def make_raw(**user_kwargs) -> RawCreatorData:
    with_loc = user_kwargs.pop("with_location", True)
    return RawCreatorData(
        user_info=make_user(**user_kwargs),
        post_info=make_posts(with_location=with_loc),
        scraped_timestamp=_ts(0),
    )
