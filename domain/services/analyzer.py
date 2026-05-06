"""Orchestrator that produces a complete AnalyzedCreator from raw data."""
from __future__ import annotations
import datetime as dt
from typing import Any, Dict, Optional

from ..models import RawCreatorData, AnalyzedCreator
from ._shapes import post_edges
from .basic_info import extract_basic_info
from .gender import identify_gender
from .social_links import extract_social_links
from .contact import extract_email, extract_phone
from .names import extract_names
from .creator_size import determine_creator_size
from .niche import identify_niche
from .collaborations import identify_collaborations
from .engagement import calculate_top_post_er
from .hashtags import extract_hashtags_and_mentions
from .locations import (
    extract_location_from_posts, parse_address, infer_location_from_profile,
)
from .pricing import extract_creator_pricing
from .posts_meta import get_latest_post_info, get_all_captions


def analyze(raw: RawCreatorData) -> Optional[AnalyzedCreator]:
    """Pure: returns an AnalyzedCreator dict, or None if data is unusable."""
    if not raw or not raw.user_info or not raw.post_info:
        return None
    posts = post_edges(raw.post_info)
    if not posts:
        return None

    basic = extract_basic_info(raw.user_info)
    first, last = extract_names(raw.user_info)

    total_recent, top6, avg_er = calculate_top_post_er(raw.user_info, raw.post_info)
    collabs = identify_collaborations(posts)
    niche = identify_niche(raw.user_info, posts)
    pricing = extract_creator_pricing(raw.user_info, posts)
    hashtags = extract_hashtags_and_mentions(posts, limit=10)
    latest = get_latest_post_info(raw.post_info)
    captions = get_all_captions(raw.post_info)

    # Deep location info
    loc = extract_location_from_posts(posts)
    primary = next(
        (l for l in loc["all_locations"] if l["name"] == loc["primary_location"]),
        None,
    )
    addr = parse_address(
        loc["primary_location"],
        primary.get("address") if primary else None,
        primary.get("city") if primary else None,
    )
    # Profile-level fallback when posts lacked any geotag.
    if not addr["country"] and not addr["city"]:
        addr = infer_location_from_profile(
            basic.get("biography"), basic.get("city_name"), basic.get("zip_code"),
        )

    scraped_date = (
        dt.datetime.fromtimestamp(raw.scraped_timestamp).strftime("%Y-%m-%d")
        if raw.scraped_timestamp else dt.datetime.now().strftime("%Y-%m-%d")
    )

    out: Dict[str, Any] = {
        # identity
        "id": basic["id"],
        "account_type": basic["account_type"],
        "username": basic["username"],
        "is_business": basic["is_business"],
        "is_verified": basic["is_verified"],
        "is_private": basic["is_private"],

        # address (profile-level, plus deep post-derived)
        "address_street": basic["address_street"],
        "city_name": basic["city_name"],
        "zip_code": basic["zip_code"],
        "external_url": basic["external_url"],
        "primary_location_name": loc["primary_location"],
        "latitude": loc["primary_lat"],
        "longitude": loc["primary_lng"],
        "address_city": addr["city"],
        "address_state": addr["state"],
        "address_country": addr["country"],
        "all_locations": loc["all_locations"],
        "posts_with_location": loc["posts_with_location"],
        "total_posts_scraped": loc["total_posts"],

        # name + bio
        "full_name": basic["full_name"],
        "first_name": first,
        "last_name": last,
        "biography": basic["biography"],
        "phone_number": extract_phone(raw.user_info),
        "email": extract_email(raw.user_info),

        # counts
        "follower_count": basic["follower_count"],
        "following_count": basic["following_count"],
        "media_count": basic["media_count"],
        "creator_size": determine_creator_size(raw.user_info),
        "gender": identify_gender(raw.user_info),

        # business
        "business_category": basic["category"],
        "profile_picture": basic["profile_picture"],
        "social_links": extract_social_links(raw.user_info),

        # engagement
        "total_posts_last_3_months": total_recent,
        "top_6_posts": top6,
        "average_engagement_rate": avg_er,

        # collabs
        "collaboration_status": collabs["status"],
        "total_collaborations": collabs["total_collaborations"],
        "recent_collaborations": collabs["recent_collaborations"],
        "ugc_examples": collabs["ugc_examples"],
        "top_collaboration": collabs["all_collaborations"],

        # niche + pricing
        "niche_data": niche,
        "creator_type": pricing["creator_type"],
        "tier": pricing["tier"],
        "creator_pricing_metrics": pricing["creator_pricing_metrics"],

        # hashtags
        "hashtags_last_90_days": hashtags["hashtags"],
        "mentions_last_90_days": hashtags["mentions"],
        "posts_analyzed_for_hashtags": hashtags["total_posts_analyzed"],
        "hashtag_analysis_date_range": hashtags["date_range"],

        # latest
        "latest_post_date": latest.get("latest_post_date"),
        "latest_post_link": latest.get("latest_post_link"),

        # bookkeeping
        "analyzed_date": dt.datetime.now().strftime("%Y-%m-%d"),
        "scraped_date": scraped_date,
        "all_posts_caption": captions.get("all_posts_caption"),
    }

    return AnalyzedCreator(out)
