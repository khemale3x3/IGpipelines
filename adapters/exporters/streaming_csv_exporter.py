"""Streaming CSV exporter (uses ijson, mirrors jsontocsv.py shape)."""
from __future__ import annotations
import csv
import os
from typing import Iterable, Optional

import ijson  # type: ignore

from ...ports.name_provider import FirstNameValidatorPort
from ..name_providers.ssa_name_provider import PassthroughFirstNameValidator

CHUNK_SIZE = 10_000

HEADERS = [
    "id", "account_type", "email", "primary_social_link", "username",
    "first_name", "last_name", "creator_type",
    "address_city", "address_state", "address_country", "address_zip",
    "collaboration_status", "top_collaboration", "top_collaboration_brand_logo",
    "hashtags", "niche_primary", "niche_secondary", "follower_count",
    "creator_size", "age_group", "age", "gender", "phone_number",
    "profile_picture", "tiktok_link", "youtube_link", "x_link",
    "linktree_link", "other_social_media", "business_category", "mention",
    "latitude", "longitude", "street_address", "bio_data", "last_updated",
    "source", "total_posts_in_3_months", "average_er_in_3_months",
    "total_collaborations", "ugc_examples", "tier", "price_usd",
    "time_15_seconds", "time_30_seconds", "time_60_seconds",
    "time_1_to_5_minutes", "time_greater_than_5_minutes",
    "latest_post_link", "latest_post_date",
    "estimated_roi", "impressions_visibility", "expected_impressions_visibility",
    "scraped_date", "analyzed_date",
] + [f"post{i+1}_interaction_score" for i in range(6)]


def _row_for(creator: dict, name_validator: FirstNameValidatorPort) -> list:
    username = creator.get("username", "") or ""
    first_name = name_validator.normalize(creator.get("first_name", "") or "", username)

    top_collab_list = [
        c.get("name") for c in (creator.get("top_collaboration") or [])
        if c.get("source") == "paid_partnership"
    ]
    top_collab_str = " | ".join(t for t in top_collab_list if t)

    top_logos = []
    for c in creator.get("top_collaboration") or []:
        if c.get("source") == "paid_partnership":
            n = (c.get("name") or "").strip()
            if n:
                top_logos.append(f"{n};https://assets.veelapp.com/{n}.jpg")
    top_collab_brand_logo = " | ".join(top_logos)

    hashtags = creator.get("hashtags_last_90_days") or {}
    h_sorted = sorted(hashtags.items(), key=lambda x: x[1], reverse=True)
    h_top = [t for t, _ in (h_sorted[:10] if len(h_sorted) >= 10 else h_sorted[:5])]
    hashtags_pipe = " | ".join(h_top)

    mentions = creator.get("mentions_last_90_days") or {}
    m_sorted = sorted(mentions.items(), key=lambda x: x[1], reverse=True)
    m_top = [m for m, _ in (m_sorted[:10] if len(m_sorted) >= 10 else m_sorted[:5])]
    mentions_pipe = " | ".join(m_top)

    socials = creator.get("social_links") or {}
    tiktok = socials.get("tiktok") or ""
    youtube = socials.get("youtube") or ""
    x_link = socials.get("x") or ""
    linktree = socials.get("linktree") or ""
    other = " | ".join(s for s in (tiktok, youtube, x_link, linktree) if s)

    pm = creator.get("creator_pricing_metrics") or {}

    row = [
        creator.get("id", ""),
        creator.get("account_type", ""),
        creator.get("email", "") or "",
        f"https://www.instagram.com/{username}" if username else "",
        username,
        first_name,
        creator.get("last_name", "") or "",
        creator.get("creator_type", ""),
        creator.get("address_city", "") or "",
        creator.get("address_state", "") or "",
        creator.get("address_country", "") or "",
        creator.get("zip_code", "") or "",
        creator.get("collaboration_status", "") or "",
        top_collab_str,
        top_collab_brand_logo,
        hashtags_pipe,
        (creator.get("niche_data") or {}).get("overall_niche", ""),
        "",  # niche_secondary (not yet computed)
        creator.get("follower_count", 0),
        creator.get("creator_size", "") or "",
        "",  # age_group
        "",  # age
        creator.get("gender", "") or "",
        creator.get("phone_number", "") or "",
        creator.get("profile_picture", "") or "",
        tiktok, youtube, x_link, linktree, other,
        creator.get("business_category", "") or "",
        mentions_pipe,
        creator.get("latitude", "") or "",
        creator.get("longitude", "") or "",
        creator.get("address_street", "") or "",
        (creator.get("biography") or "").replace("\n", " "),
        creator.get("analyzed_date", "") or "",
        "",  # source
        creator.get("total_posts_last_3_months", 0) or 0,
        creator.get("average_engagement_rate", 0) or 0,
        creator.get("total_collaborations", 0) or 0,
        creator.get("ugc_examples", "") or "",
        creator.get("tier", "") or "",
        pm.get("price_usd", "") or "",
        pm.get("time_15_seconds", "") or "",
        pm.get("time_30_seconds", "") or "",
        pm.get("time_60_seconds", "") or "",
        pm.get("time_1_to_5_minutes", "") or "",
        pm.get("time_greater_than_5_minutes", "") or "",
        creator.get("latest_post_link", "") or "",
        creator.get("latest_post_date", "") or "",
        pm.get("estimated_roi", "") or "",
        pm.get("impressions_visibility", "") or "",
        pm.get("expected_impressions_visibility", "") or "",
        creator.get("scraped_date", "") or "",
        creator.get("analyzed_date", "") or "",
    ]

    top_posts = creator.get("top_6_posts") or []
    for i in range(6):
        row.append(top_posts[i].get("interaction_score", 0) if i < len(top_posts) else "")

    return row


class StreamingCsvExporter:
    def __init__(self, name_validator: Optional[FirstNameValidatorPort] = None) -> None:
        self.name_validator = name_validator or PassthroughFirstNameValidator()

    def export(self, analyzed_json_path: str, output_path: str) -> int:
        if not os.path.exists(analyzed_json_path):
            raise FileNotFoundError(analyzed_json_path)

        total = 0
        chunk: list = []
        with open(output_path, "w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out, quoting=csv.QUOTE_ALL)
            writer.writerow(HEADERS)
            with open(analyzed_json_path, "rb") as fh:
                for creator in ijson.items(fh, "creators.item"):
                    chunk.append(_row_for(creator, self.name_validator))
                    total += 1
                    if len(chunk) >= CHUNK_SIZE:
                        writer.writerows(chunk)
                        chunk.clear()
                if chunk:
                    writer.writerows(chunk)
        return total
