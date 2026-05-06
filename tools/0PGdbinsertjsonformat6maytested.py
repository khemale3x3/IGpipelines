"""
insert_creators.py — Full Insert Script v4.0 (Optimized)
===========================================================
Reads analyzed.json and inserts ALL records into analyze.* schema.
Covers every table defined in schema.sql — zero data points skipped.

Optimizations:
  - Batched inserts with psycopg2.extras.execute_values
  - Posts inserted in bulk, child records batched per table
  - Reduced round trips from thousands to ~20 per creator

Usage:
    pip install psycopg2-binary
    python insert_creators.py                        # prompts for file path
    python insert_creators.py --file analyzed.json   # or pass it directly

Options:
    --file PATH     Path to analyzed.json  (default: prompt)
    --schema NAME   PostgreSQL schema name  (default: analyze)
    --truncate      Truncate all tables before insert (fresh load)
"""

import json
import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Optional

try:
    import psycopg2
    from psycopg2.extras import execute_values, Json
except ImportError:
    print("ERROR: psycopg2 not installed.  Run:  pip install psycopg2-binary")
    sys.exit(1)


# ── DB connection ──────────────────────────────────────────────────────────────
def get_connection():
    return psycopg2.connect(
        host     = os.getenv("DB_HOST",     "d----b host"),
        port     = int(os.getenv("DB_PORT", "5432")),
        dbname   = os.getenv("DB_NAME",     "database"),
        user     = os.getenv("DB_USER",     "postgres"),
        password = os.getenv("DB_PASSWORD", "passw0rd"),
    )


# ── Helpers ────────────────────────────────────────────────────────────────────
SCHEMA = "analyze"   # overridable via CLI

def tbl(name: str) -> str:
    """Qualify table with schema — double-quote schema to escape reserved keywords."""
    return f'"{SCHEMA}".{name}'


def safe_date(val) -> Optional[str]:
    if not val:
        return None
    if isinstance(val, str):
        return val.split("T")[0].split(" ")[0] or None
    return None


def safe_ts(val) -> Optional[str]:
    if not val:
        return None
    return str(val)


def safe_int(val, default=None):
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def safe_float(val, default=None):
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def j(val) -> Optional[Json]:
    """Wrap dict/list as psycopg2 Json or return None."""
    return Json(val) if val is not None else None


def arr(val) -> list:
    """Ensure list."""
    if isinstance(val, list):
        return val
    return []


# ── Batching helpers ──────────────────────────────────────────────────────────
def batch_insert(cur, table: str, columns: list, rows: list, conflict: str = None):
    """
    Execute a batch INSERT using execute_values.
    - table: qualified table name (use tbl() helper)
    - columns: list of column names
    - rows: list of tuples, each matching columns
    - conflict: optional ON CONFLICT clause (e.g., "ON CONFLICT (id) DO NOTHING")
    """
    if not rows:
        return
    cols = ', '.join(columns)
    sql = f"INSERT INTO {table} ({cols}) VALUES %s"
    if conflict:
        sql += f" {conflict}"
    execute_values(cur, sql, rows, page_size=1000)


def batch_insert_posts(cur, rows: list) -> dict:
    """
    Batch insert posts and return a dict {code: post_id}.
    rows: list of tuples matching posts table columns (must include 'code' as last element)
    """
    if not rows:
        return {}
    # Columns must match the INSERT order in insert_creator_posts
    columns = [
        "creator_id", "post_pk", "post_id", "code", "post_url", "typename",
        "media_type", "product_type", "original_width", "original_height", "aspect_ratio",
        "caption_text", "caption_pk", "caption_created_at", "caption_is_edited",
        "caption_has_translation", "accessibility_caption", "title", "headline", "taken_at",
        "like_count", "comment_count", "view_count", "fb_like_count", "media_repost_count",
        "like_and_view_counts_disabled", "hidden_likes_string_variant",
        "has_liked", "has_viewer_saved", "photo_of_you",
        "is_paid_partnership", "sponsor_tags", "affiliate_info", "is_ad", "ad_tags_found",
        "has_audio", "is_dash_eligible", "number_of_qualities",
        "carousel_media_count", "carousel_parent_id",
        "location_pk", "location_name", "location_lat", "location_lng",
        "location_address", "location_city",
        "can_reshare", "can_viewer_reshare", "ig_media_sharing_disabled", "is_shared_from_basel",
        "owner_id", "poster_username", "poster_full_name", "poster_is_verified", "poster_profile_pic_url",
        "boosted_status", "boost_unavailable_identifier", "boost_unavailable_reason",
        "clips_audio_type", "clips_is_shared_to_fb", "clips_original_audio_title",
        "clips_audio_asset_id", "clips_ig_artist_username", "clips_is_explicit",
        "timeline_pinned_user_ids", "inventory_source", "audience",
        "profile_grid_thumbnail_style", "is_seen",
        "hashtags_in_caption", "mentions_in_caption",
        "hashtag_count", "mention_count", "caption_word_count", "caption_char_count"
    ]
    cols = ', '.join(columns)
    # Conflict: update like/comment/view counts if post already exists
    conflict_sql = "ON CONFLICT (post_pk) DO UPDATE SET like_count = EXCLUDED.like_count, comment_count = EXCLUDED.comment_count, view_count = EXCLUDED.view_count RETURNING id, code"
    sql = f"INSERT INTO {tbl('posts')} ({cols}) VALUES %s {conflict_sql}"
    results = execute_values(cur, sql, rows, page_size=1000, fetch=True)
    # results is list of (id, code) tuples
    return {code: pid for pid, code in results}


# ── 1. CREATORS ────────────────────────────────────────────────────────────────
def insert_creator(cur, c: dict) -> int:
    pricing = c.get("creator_pricing_metrics") or {}
    health  = c.get("health_breakdown") or {}
    content = c.get("content_dna") or {}
    caps    = c.get("caption_intelligence") or {}

    cur.execute(
        f"""
        INSERT INTO {tbl("creators")} (
            username, full_name, first_name, last_name, biography,
            pk, fbid_v2, account_type,
            is_verified, is_business, is_private, is_professional_account,
            is_unpublished, is_memorialized, is_coppa_enforced, is_regulated_c18,
            is_ring_creator, is_embeds_disabled, is_cannes, show_ring_award,
            show_text_post_app_badge, remove_message_entrypoint,
            hide_creator_marketplace_badge, has_chaining,
            follower_count, following_count, media_count, total_clips_count,
            ff_ratio, creator_size,
            email, phone_number, external_url, external_lynx_url,
            profile_picture_url, profile_picture_local, has_profile_pic,
            category, business_category, should_show_category,
            address_street, city_name, zip,
            ai_agent_type, transparency_label, transparency_product,
            latest_reel_media, latest_besties_reel_media, has_story_archive,
            reel_media_seen_timestamp,
            gender, primary_niche,
            creator_type, tier,
            avg_likes, avg_comments, avg_er_weighted, avg_er_simple,
            avg_er_top6, avg_er_last_90_days, er_grade,
            like_comment_ratio, audience_engagement_type, viral_posts_count,
            collaboration_status, is_brand_active, paid_partnership_posts,
            ad_tagged_posts, total_unique_brands, total_collaborations, recent_collaborations,
            primary_location_name, primary_lat, primary_lng,
            address_city, address_state, address_country,
            posts_with_location, unique_locations, is_traveler, unique_coords_count,
            total_posts_scraped, total_posts_last_3_months,
            dominant_format, posts_with_caption_pct, posts_with_location_pct,
            posts_with_usertags_pct, avg_caption_length_chars, avg_caption_words,
            caption_style, avg_carousel_slides, avg_days_between_posts,
            estimated_posts_per_week, estimated_posts_per_month,
            posting_consistency_score, first_post_date, last_post_date,
            days_span_scraped, days_since_last_post, activity_status,
            primary_language, emoji_usage_pct, avg_hashtags_per_post,
            avg_mentions_per_post, hashtag_strategy, uses_cta,
            posts_with_captions, hashtag_count_total, unique_hashtags,
            creator_archetype, archetype_description,
            growth_health_score, health_grade,
            estimated_roi, impressions_visibility,
            price_15s_usd, price_30s_usd, price_60s_usd,
            price_1_5min_usd, price_5plus_min_usd, price_story_usd, price_carousel_usd,
            ugc_examples, hashtag_analysis_date_range, posts_analyzed_for_hashtags,
            latest_post_date, latest_post_link,
            analyzed_date, scraped_date
        )
        VALUES (
            %(username)s, %(full_name)s, %(first_name)s, %(last_name)s, %(biography)s,
            %(pk)s, %(fbid_v2)s, %(account_type)s,
            %(is_verified)s, %(is_business)s, %(is_private)s, %(is_professional_account)s,
            %(is_unpublished)s, %(is_memorialized)s, %(is_coppa_enforced)s, %(is_regulated_c18)s,
            %(is_ring_creator)s, %(is_embeds_disabled)s, %(is_cannes)s, %(show_ring_award)s,
            %(show_text_post_app_badge)s, %(remove_message_entrypoint)s,
            %(hide_creator_marketplace_badge)s, %(has_chaining)s,
            %(follower_count)s, %(following_count)s, %(media_count)s, %(total_clips_count)s,
            %(ff_ratio)s, %(creator_size)s,
            %(email)s, %(phone_number)s, %(external_url)s, %(external_lynx_url)s,
            %(profile_picture_url)s, %(profile_picture_local)s, %(has_profile_pic)s,
            %(category)s, %(business_category)s, %(should_show_category)s,
            %(address_street)s, %(city_name)s, %(zip)s,
            %(ai_agent_type)s, %(transparency_label)s, %(transparency_product)s,
            %(latest_reel_media)s, %(latest_besties_reel_media)s, %(has_story_archive)s,
            %(reel_media_seen_timestamp)s,
            %(gender)s, %(primary_niche)s,
            %(creator_type)s, %(tier)s,
            %(avg_likes)s, %(avg_comments)s, %(avg_er_weighted)s, %(avg_er_simple)s,
            %(avg_er_top6)s, %(avg_er_last_90_days)s, %(er_grade)s,
            %(like_comment_ratio)s, %(audience_engagement_type)s, %(viral_posts_count)s,
            %(collaboration_status)s, %(is_brand_active)s, %(paid_partnership_posts)s,
            %(ad_tagged_posts)s, %(total_unique_brands)s, %(total_collaborations)s, %(recent_collaborations)s,
            %(primary_location_name)s, %(primary_lat)s, %(primary_lng)s,
            %(address_city)s, %(address_state)s, %(address_country)s,
            %(posts_with_location)s, %(unique_locations)s, %(is_traveler)s, %(unique_coords_count)s,
            %(total_posts_scraped)s, %(total_posts_last_3_months)s,
            %(dominant_format)s, %(posts_with_caption_pct)s, %(posts_with_location_pct)s,
            %(posts_with_usertags_pct)s, %(avg_caption_length_chars)s, %(avg_caption_words)s,
            %(caption_style)s, %(avg_carousel_slides)s, %(avg_days_between_posts)s,
            %(estimated_posts_per_week)s, %(estimated_posts_per_month)s,
            %(posting_consistency_score)s, %(first_post_date)s, %(last_post_date)s,
            %(days_span_scraped)s, %(days_since_last_post)s, %(activity_status)s,
            %(primary_language)s, %(emoji_usage_pct)s, %(avg_hashtags_per_post)s,
            %(avg_mentions_per_post)s, %(hashtag_strategy)s, %(uses_cta)s,
            %(posts_with_captions)s, %(hashtag_count_total)s, %(unique_hashtags)s,
            %(creator_archetype)s, %(archetype_description)s,
            %(growth_health_score)s, %(health_grade)s,
            %(estimated_roi)s, %(impressions_visibility)s,
            %(price_15s_usd)s, %(price_30s_usd)s, %(price_60s_usd)s,
            %(price_1_5min_usd)s, %(price_5plus_min_usd)s, %(price_story_usd)s, %(price_carousel_usd)s,
            %(ugc_examples)s, %(hashtag_analysis_date_range)s, %(posts_analyzed_for_hashtags)s,
            %(latest_post_date)s, %(latest_post_link)s,
            %(analyzed_date)s, %(scraped_date)s
        )
        ON CONFLICT (username) DO UPDATE SET
            full_name                 = EXCLUDED.full_name,
            follower_count            = EXCLUDED.follower_count,
            following_count           = EXCLUDED.following_count,
            avg_er_weighted           = EXCLUDED.avg_er_weighted,
            growth_health_score       = EXCLUDED.growth_health_score,
            total_posts_last_3_months = EXCLUDED.total_posts_last_3_months,
            collaboration_status      = EXCLUDED.collaboration_status,
            latest_post_date          = EXCLUDED.latest_post_date,
            scraped_date              = EXCLUDED.scraped_date,
            analyzed_date             = EXCLUDED.analyzed_date,
            updated_at                = NOW()
        RETURNING id
        """,
        {
            "username":                   c.get("username"),
            "full_name":                  c.get("full_name"),
            "first_name":                 c.get("first_name"),
            "last_name":                   c.get("last_name"),
            "biography":                   c.get("biography"),
            "pk":                          c.get("pk"),
            "fbid_v2":                     c.get("fbid_v2"),
            "account_type":                safe_int(c.get("account_type")),
            "is_verified":                 bool(c.get("is_verified")),
            "is_business":                  bool(c.get("is_business")),
            "is_private":                   bool(c.get("is_private")),
            "is_professional_account":      c.get("is_professional_account"),
            "is_unpublished":                bool(c.get("is_unpublished")),
            "is_memorialized":               bool(c.get("is_memorialized")),
            "is_coppa_enforced":             bool(c.get("is_coppa_enforced")),
            "is_regulated_c18":              bool(c.get("is_regulated_c18")),
            "is_ring_creator":               bool(c.get("is_ring_creator")),
            "is_embeds_disabled":            bool(c.get("is_embeds_disabled")),
            "is_cannes":                     bool(c.get("is_cannes")),
            "show_ring_award":                bool(c.get("show_ring_award")),
            "show_text_post_app_badge":       bool(c.get("show_text_post_app_badge")),
            "remove_message_entrypoint":      bool(c.get("remove_message_entrypoint")),
            "hide_creator_marketplace_badge": bool(c.get("hide_creator_marketplace_badge")),
            "has_chaining":                   bool(c.get("has_chaining")),
            "follower_count":                 safe_int(c.get("follower_count"), 0),
            "following_count":                 safe_int(c.get("following_count"), 0),
            "media_count":                     safe_int(c.get("media_count"), 0),
            "total_clips_count":               safe_int(c.get("total_clips_count"), 0),
            "ff_ratio":                        safe_float(c.get("ff_ratio")),
            "creator_size":                    c.get("creator_size"),
            "email":                           c.get("email"),
            "phone_number":                    c.get("phone_number"),
            "external_url":                    c.get("external_url"),
            "external_lynx_url":               c.get("external_lynx_url"),
            "profile_picture_url":             c.get("profile_picture_url"),
            "profile_picture_local":           c.get("profile_picture_local"),
            "has_profile_pic":                  c.get("has_profile_pic"),
            "category":                         c.get("category"),
            "business_category":                c.get("business_category"),
            "should_show_category":             bool(c.get("should_show_category")),
            "address_street":                   c.get("address_street"),
            "city_name":                        c.get("city_name"),
            "zip":                              c.get("zip"),
            "ai_agent_type":                    c.get("ai_agent_type"),
            "transparency_label":                c.get("transparency_label"),
            "transparency_product":              c.get("transparency_product"),
            "latest_reel_media":                 safe_int(c.get("latest_reel_media"), 0),
            "latest_besties_reel_media":         safe_int(c.get("latest_besties_reel_media"), 0),
            "has_story_archive":                 c.get("has_story_archive"),
            "reel_media_seen_timestamp":         c.get("reel_media_seen_timestamp"),
            "gender":                            c.get("gender"),
            "primary_niche":                     c.get("primary_niche"),
            "creator_type":                      c.get("creator_type"),
            "tier":                              c.get("tier"),
            "avg_likes":                         safe_float(c.get("avg_likes")),
            "avg_comments":                      safe_float(c.get("avg_comments")),
            "avg_er_weighted":                    safe_float(c.get("avg_er_weighted")),
            "avg_er_simple":                      safe_float(c.get("avg_er_simple")),
            "avg_er_top6":                        safe_float(c.get("avg_er_top6")),
            "avg_er_last_90_days":                safe_float(c.get("avg_er_last_90_days")),
            "er_grade":                           c.get("er_grade"),
            "like_comment_ratio":                 safe_float(c.get("like_comment_ratio")),
            "audience_engagement_type":           c.get("audience_engagement_type"),
            "viral_posts_count":                  safe_int(c.get("viral_posts_count"), 0),
            "collaboration_status":                c.get("collaboration_status"),
            "is_brand_active":                     bool(c.get("is_brand_active")),
            "paid_partnership_posts":              safe_int(c.get("paid_partnership_posts"), 0),
            "ad_tagged_posts":                     safe_int(c.get("ad_tagged_posts"), 0),
            "total_unique_brands":                 safe_int(c.get("total_unique_brands"), 0),
            "total_collaborations":                 safe_int(c.get("total_collaborations"), 0),
            "recent_collaborations":                safe_int(c.get("recent_collaborations"), 0),
            "primary_location_name":                c.get("primary_location_name"),
            "primary_lat":                          safe_float(c.get("primary_lat")),
            "primary_lng":                          safe_float(c.get("primary_lng")),
            "address_city":                         c.get("address_city"),
            "address_state":                        c.get("address_state"),
            "address_country":                      c.get("address_country"),
            "posts_with_location":                  safe_int(c.get("posts_with_location"), 0),
            "unique_locations":                     safe_int(c.get("unique_locations"), 0),
            "is_traveler":                           bool(c.get("is_traveler")),
            "unique_coords_count":                   safe_int(c.get("unique_coords_count"), 0),
            "total_posts_scraped":                   safe_int(c.get("total_posts_scraped"), 0),
            "total_posts_last_3_months":             safe_int(c.get("total_posts_last_3_months"), 0),
            "dominant_format":                       content.get("dominant_format"),
            "posts_with_caption_pct":                safe_float(content.get("posts_with_caption_pct")),
            "posts_with_location_pct":                safe_float(content.get("posts_with_location_pct")),
            "posts_with_usertags_pct":                safe_float(content.get("posts_with_usertags_pct")),
            "avg_caption_length_chars":               safe_int(content.get("avg_caption_length_chars")),
            "avg_caption_words":                      safe_int(content.get("avg_caption_words")),
            "caption_style":                          content.get("caption_style"),
            "avg_carousel_slides":                    safe_float(content.get("avg_carousel_slides")),
            "avg_days_between_posts":                 safe_float(content.get("avg_days_between_posts")),
            "estimated_posts_per_week":                safe_float(content.get("estimated_posts_per_week")),
            "estimated_posts_per_month":               safe_float(content.get("estimated_posts_per_month")),
            "posting_consistency_score":               safe_int(content.get("posting_consistency_score")),
            "first_post_date":                         safe_date(content.get("first_post_date")),
            "last_post_date":                          safe_date(content.get("last_post_date")),
            "days_span_scraped":                       safe_int(content.get("days_span_scraped")),
            "days_since_last_post":                    safe_int(content.get("days_since_last_post")),
            "activity_status":                         content.get("activity_status"),
            "primary_language":                        caps.get("primary_language"),
            "emoji_usage_pct":                         safe_float(caps.get("emoji_usage_pct")),
            "avg_hashtags_per_post":                   safe_float(caps.get("avg_hashtags_per_post")),
            "avg_mentions_per_post":                   safe_float(caps.get("avg_mentions_per_post")),
            "hashtag_strategy":                        caps.get("hashtag_strategy"),
            "uses_cta":                                bool(caps.get("uses_cta")),
            "posts_with_captions":                     safe_int(caps.get("posts_with_captions"), 0),
            "hashtag_count_total":                     safe_int(c.get("hashtag_count_total"), 0),
            "unique_hashtags":                         safe_int(c.get("unique_hashtags_total"), 0),
            "creator_archetype":                       c.get("creator_archetype"),
            "archetype_description":                   c.get("archetype_description"),
            "growth_health_score":                     safe_int(c.get("growth_health_score")),
            "health_grade":                             c.get("health_grade"),
            "estimated_roi":                            pricing.get("estimated_roi"),
            "impressions_visibility":                   pricing.get("impressions_visibility"),
            "price_15s_usd":                            safe_int(pricing.get("time_15_seconds")),
            "price_30s_usd":                            safe_int(pricing.get("time_30_seconds")),
            "price_60s_usd":                            safe_int(pricing.get("time_60_seconds")),
            "price_1_5min_usd":                         safe_int(pricing.get("time_1_to_5_minutes")),
            "price_5plus_min_usd":                      safe_int(pricing.get("time_greater_5_minutes")),
            "price_story_usd":                          safe_int(pricing.get("story_usd")),
            "price_carousel_usd":                       safe_int(pricing.get("carousel_usd")),
            "ugc_examples":                             c.get("ugc_examples"),
            "hashtag_analysis_date_range":              c.get("hashtag_analysis_date_range"),
            "posts_analyzed_for_hashtags":              safe_int(c.get("posts_analyzed_for_hashtags"), 0),
            "latest_post_date":                         safe_ts(c.get("latest_post_date")),
            "latest_post_link":                         c.get("latest_post_link"),
            "analyzed_date":                             safe_date(c.get("analyzed_date")),
            "scraped_date":                              safe_date(c.get("scraped_date")),
        }
    )
    return cur.fetchone()[0]


# ── DELETE child rows on update ────────────────────────────────────────────────
CHILD_TABLES_BY_FK = [
    ("creator_social_links",        "creator_id"),
    ("creator_bio_links",           "creator_id"),
    ("creator_viewer_status",       "creator_id"),
    ("creator_profile_images",      "creator_id"),
    ("creator_locations",           "creator_id"),
    ("creator_hashtags",            "creator_id"),
    ("creator_mentions",            "creator_id"),
    ("creator_collaborations",      "creator_id"),
    ("creator_niche_data",          "creator_id"),
    ("creator_niche_distribution",  "creator_id"),
    ("creator_pricing_metrics",     "creator_id"),
    ("creator_content_dna",         "creator_id"),
    ("creator_caption_intelligence","creator_id"),
    ("creator_engagement_analytics","creator_id"),
    ("creator_health_scores",       "creator_id"),
    ("creator_brand_intelligence",  "creator_id"),
]

POST_CHILD_TABLES = [
    ("post_image_versions",  "post_id"),
    ("post_video_versions",  "post_id"),
    ("post_carousel_items",  "post_id"),
    ("post_usertags",        "post_id"),
    ("post_coauthors",       "post_id"),
    ("post_top_likers",      "post_id"),
]


def delete_creator_children(cur, creator_id: int):
    cur.execute(f"SELECT id FROM {tbl('posts')} WHERE creator_id = %s", (creator_id,))
    post_ids = [r[0] for r in cur.fetchall()]
    if post_ids:
        for child_tbl, fk in POST_CHILD_TABLES:
            cur.execute(f"DELETE FROM {tbl(child_tbl)} WHERE {fk} = ANY(%s)", (post_ids,))
    cur.execute(f"DELETE FROM {tbl('posts')} WHERE creator_id = %s", (creator_id,))
    for child_tbl, fk in CHILD_TABLES_BY_FK:
        cur.execute(f"DELETE FROM {tbl(child_tbl)} WHERE {fk} = %s", (creator_id,))


# ── MASTER INSERT (batched) ─────────────────────────────────────────────────────
def insert_full_creator(cur, c: dict) -> int:
    # Insert creator (single row)
    creator_id = insert_creator(cur, c)
    # Remove old child data
    delete_creator_children(cur, creator_id)

    # ------------------------------------------------------------------
    # 1. POSTS and their children (batched)
    # ------------------------------------------------------------------
    posts_rows = []
    post_image_versions_rows = []
    post_video_versions_rows = []
    post_carousel_items_rows = []
    post_usertags_rows = []
    post_coauthors_rows = []
    post_top_likers_rows = []

    for p in c.get("posts") or []:
        posts_rows.append((
            creator_id,
            p.get("post_pk"),
            p.get("post_id"),
            p.get("code"),
            p.get("post_url"),
            p.get("typename"),
            safe_int(p.get("media_type")),
            p.get("product_type"),
            safe_int(p.get("original_width")),
            safe_int(p.get("original_height")),
            safe_float(p.get("aspect_ratio")),
            p.get("caption_text"),
            p.get("caption_pk"),
            safe_ts(p.get("caption_created_at")),
            bool(p.get("caption_is_edited")),
            p.get("caption_has_translation"),
            p.get("accessibility_caption"),
            p.get("title"),
            p.get("headline"),
            safe_ts(p.get("taken_at")),
            safe_int(p.get("like_count"), 0),
            safe_int(p.get("comment_count"), 0),
            safe_int(p.get("view_count")),
            safe_int(p.get("fb_like_count")),
            safe_int(p.get("media_repost_count")),
            bool(p.get("like_and_view_counts_disabled")),
            safe_int(p.get("hidden_likes_string_variant")),
            bool(p.get("has_liked")),
            p.get("has_viewer_saved"),
            bool(p.get("photo_of_you")),
            bool(p.get("is_paid_partnership")),
            j(p.get("sponsor_tags")),
            p.get("affiliate_info"),
            bool(p.get("is_ad")),
            arr(p.get("ad_tags_found")),
            p.get("has_audio"),
            bool(p.get("is_dash_eligible")),
            safe_int(p.get("number_of_qualities")),
            safe_int(p.get("carousel_media_count")),
            p.get("carousel_parent_id"),
            p.get("location_pk"),
            p.get("location_name"),
            safe_float(p.get("location_lat")),
            safe_float(p.get("location_lng")),
            p.get("location_address"),
            p.get("location_city"),
            p.get("can_reshare"),
            bool(p.get("can_viewer_reshare")),
            bool(p.get("ig_media_sharing_disabled")),
            p.get("is_shared_from_basel"),
            p.get("owner_id"),
            p.get("poster_username"),
            p.get("poster_full_name"),
            bool(p.get("poster_is_verified")),
            p.get("poster_profile_pic_url"),
            p.get("boosted_status"),
            p.get("boost_unavailable_identifier"),
            p.get("boost_unavailable_reason"),
            p.get("clips_audio_type"),
            p.get("clips_is_shared_to_fb"),
            p.get("clips_original_audio_title"),
            p.get("clips_audio_asset_id"),
            p.get("clips_ig_artist_username"),
            p.get("clips_is_explicit"),
            arr(p.get("timeline_pinned_user_ids")),
            p.get("inventory_source"),
            p.get("audience"),
            p.get("profile_grid_thumbnail_style"),
            p.get("is_seen"),
            arr(p.get("hashtags_in_caption")),
            arr(p.get("mentions_in_caption")),
            safe_int(p.get("hashtag_count"), 0),
            safe_int(p.get("mention_count"), 0),
            safe_int(p.get("caption_word_count"), 0),
            safe_int(p.get("caption_char_count"), 0),
        ))

    # Insert all posts at once and get mapping code -> id
    code_to_id = batch_insert_posts(cur, posts_rows)

    # Now collect child rows for each post
    for p in c.get("posts") or []:
        code = p.get("code")
        post_id = code_to_id.get(code)
        if not post_id:
            continue  # should not happen

        # image versions
        for img in p.get("all_image_candidates") or []:
            post_image_versions_rows.append((
                post_id,
                img.get("url"),
                safe_int(img.get("width")),
                safe_int(img.get("height")),
                img.get("width") == p.get("image_width_best")
            ))

        # video versions
        for vid in p.get("all_video_versions") or []:
            post_video_versions_rows.append((
                post_id,
                vid.get("url"),
                safe_int(vid.get("width")),
                safe_int(vid.get("height")),
                safe_int(vid.get("type"))
            ))

        # carousel items
        for ci in p.get("carousel_items") or []:
            post_carousel_items_rows.append((
                post_id,
                ci.get("pk"),
                ci.get("id"),
                ci.get("carousel_parent_id"),
                safe_int(ci.get("position")),
                safe_int(ci.get("media_type")),
                safe_int(ci.get("original_width")),
                safe_int(ci.get("original_height")),
                ci.get("has_audio"),
                ci.get("is_dash_eligible"),
                ci.get("image_url"),
                ci.get("video_url")
            ))

        # usertags
        for ut in p.get("usertags") or []:
            post_usertags_rows.append((
                post_id,
                ut.get("pk"),
                ut.get("username"),
                ut.get("full_name"),
                bool(ut.get("is_verified")),
                safe_float(ut.get("position_x")),
                safe_float(ut.get("position_y"))
            ))

        # coauthors
        for ca in p.get("coauthors") or []:
            post_coauthors_rows.append((
                post_id,
                ca.get("pk"),
                ca.get("username"),
                ca.get("full_name"),
                bool(ca.get("is_verified")),
                ca.get("profile_pic_url"),
                bool(ca.get("is_invited"))
            ))

        # top likers
        for lk in p.get("top_likers") or []:
            post_top_likers_rows.append((
                post_id,
                lk.get("pk"),
                lk.get("username")
            ))

    # Batch insert all post child tables
    batch_insert(cur, tbl("post_image_versions"),
                 ["post_id", "url", "width", "height", "is_primary"],
                 post_image_versions_rows)
    batch_insert(cur, tbl("post_video_versions"),
                 ["post_id", "url", "width", "height", "video_type"],
                 post_video_versions_rows)
    batch_insert(cur, tbl("post_carousel_items"),
                 ["post_id", "item_pk", "item_id", "carousel_parent_id", "position",
                  "media_type", "original_width", "original_height", "has_audio",
                  "is_dash_eligible", "image_url", "video_url"],
                 post_carousel_items_rows)
    batch_insert(cur, tbl("post_usertags"),
                 ["post_id", "tagged_user_pk", "tagged_username", "tagged_fullname",
                  "is_verified", "position_x", "position_y"],
                 post_usertags_rows)
    batch_insert(cur, tbl("post_coauthors"),
                 ["post_id", "coauthor_pk", "coauthor_username", "coauthor_fullname",
                  "is_verified", "profile_pic_url", "is_invited"],
                 post_coauthors_rows)
    batch_insert(cur, tbl("post_top_likers"),
                 ["post_id", "liker_pk", "liker_username"],
                 post_top_likers_rows)

    # ------------------------------------------------------------------
    # 2. Creator child tables (batched)
    # ------------------------------------------------------------------
    # social_links
    sl = c.get("social_links") or {}
    batch_insert(cur, tbl("creator_social_links"),
                 ["creator_id", "tiktok", "youtube", "linktree", "twitter_x",
                  "facebook", "spotify", "other"],
                 [(creator_id,
                   sl.get("tiktok"),
                   sl.get("youtube"),
                   sl.get("linktree"),
                   sl.get("twitter_x"),
                   sl.get("facebook"),
                   sl.get("spotify"),
                   arr(sl.get("other")))])

    # bio_links
    bio_rows = []
    for lk in c.get("parsed_bio_links") or []:
        bio_rows.append((
            creator_id,
            lk.get("url"),
            lk.get("type"),
            lk.get("display_text"),
            bool(lk.get("is_pinned"))
        ))
    batch_insert(cur, tbl("creator_bio_links"),
                 ["creator_id", "url", "link_type", "display_text", "is_pinned"],
                 bio_rows)

    # viewer_status
    fs = c.get("friendship_status") or {}
    batch_insert(cur, tbl("creator_viewer_status"),
                 ["creator_id", "following", "blocking", "is_feed_favorite",
                  "outgoing_request", "followed_by", "incoming_request",
                  "is_restricted", "is_bestie", "muting", "is_muting_reel"],
                 [(creator_id,
                   bool(fs.get("following")),
                   bool(fs.get("blocking")),
                   bool(fs.get("is_feed_favorite")),
                   bool(fs.get("outgoing_request")),
                   bool(fs.get("followed_by")),
                   bool(fs.get("incoming_request")),
                   bool(fs.get("is_restricted")),
                   bool(fs.get("is_bestie")),
                   bool(fs.get("muting")),
                   bool(fs.get("is_muting_reel")))])

    # profile_images
    batch_insert(cur, tbl("creator_profile_images"),
                 ["creator_id", "instagram_url", "local_url", "hd_url", "format"],
                 [(creator_id,
                   c.get("profile_picture_url"),
                   c.get("profile_picture_local"),
                   c.get("profile_picture_url"),
                   c.get("profile_pic_format", "jpg"))])

    # locations
    loc_rows = []
    for loc in c.get("all_locations") or []:
        loc_rows.append((
            creator_id,
            loc.get("location_pk") or loc.get("id"),
            loc.get("name"),
            safe_float(loc.get("lat")),
            safe_float(loc.get("lng")),
            loc.get("address"),
            loc.get("city"),
            loc.get("post_code"),
            loc.get("post_url") or loc.get("post_link"),
            safe_date(loc.get("post_taken_at") or loc.get("date"))
        ))
    batch_insert(cur, tbl("creator_locations"),
                 ["creator_id", "location_pk", "name", "lat", "lng", "address",
                  "city", "post_code", "post_url", "post_taken_at"],
                 loc_rows)

    # hashtags
    ht_rows = []
    for tag, count in (c.get("hashtags_last_90_days") or {}).items():
        ht_rows.append((creator_id, tag, safe_int(count, 1)))
    batch_insert(cur, tbl("creator_hashtags"),
                 ["creator_id", "hashtag", "usage_count"],
                 ht_rows)

    # mentions
    men_rows = []
    for user, count in (c.get("mentions_last_90_days") or {}).items():
        men_rows.append((creator_id, user, safe_int(count, 1)))
    batch_insert(cur, tbl("creator_mentions"),
                 ["creator_id", "mentioned_user", "mention_count"],
                 men_rows)

    # collaborations
    collab_rows = []
    for brand in c.get("top_brands") or []:
        collab_rows.append((
            creator_id,
            brand.get("username"),
            safe_int(brand.get("mention_count"), 1),
            bool(brand.get("recent")),
            ','.join(set(brand.get("sources") or [])) or None,
            safe_int(brand.get("mention_count"), 1)
        ))
    batch_insert(cur, tbl("creator_collaborations"),
                 ["creator_id", "collab_username", "collab_count", "is_recent",
                  "source", "mention_count"],
                 collab_rows)

    # niche_data (single row)
    batch_insert(cur, tbl("creator_niche_data"),
                 ["creator_id", "overall_niche", "matched_keywords", "distribution"],
                 [(creator_id,
                   c.get("primary_niche"),
                   arr(c.get("niche_matched_keywords")),
                   j(c.get("niche_distribution")))])

    # niche_distribution
    nd_rows = []
    for niche_name, pct in (c.get("niche_distribution") or {}).items():
        nd_rows.append((creator_id, niche_name, safe_float(pct)))
    batch_insert(cur, tbl("creator_niche_distribution"),
                 ["creator_id", "niche_name", "percentage"],
                 nd_rows)

    # pricing_metrics
    pm = c.get("creator_pricing_metrics") or {}
    batch_insert(cur, tbl("creator_pricing_metrics"),
                 ["creator_id", "estimated_roi", "impressions_visibility",
                  "time_15_seconds_usd", "time_30_seconds_usd", "time_60_seconds_usd",
                  "time_1_to_5_minutes_usd", "time_greater_5min_usd",
                  "story_usd", "carousel_usd"],
                 [(creator_id,
                   pm.get("estimated_roi"),
                   pm.get("impressions_visibility"),
                   safe_int(pm.get("time_15_seconds")),
                   safe_int(pm.get("time_30_seconds")),
                   safe_int(pm.get("time_60_seconds")),
                   safe_int(pm.get("time_1_to_5_minutes")),
                   safe_int(pm.get("time_greater_5_minutes")),
                   safe_int(pm.get("story_usd")),
                   safe_int(pm.get("carousel_usd")))])

    # content_dna
    cd = c.get("content_dna") or {}
    batch_insert(cur, tbl("creator_content_dna"),
                 ["creator_id", "content_type_mix", "dominant_format",
                  "avg_carousel_slides", "posts_with_caption_pct",
                  "posts_with_location_pct", "posts_with_usertags_pct",
                  "avg_caption_length_chars", "avg_caption_words", "caption_style",
                  "first_post_date", "last_post_date", "days_span_scraped",
                  "days_since_last_post", "activity_status", "avg_days_between_posts",
                  "estimated_posts_per_week", "estimated_posts_per_month",
                  "posting_consistency_score"],
                 [(creator_id,
                   j(cd.get("content_type_mix")),
                   cd.get("dominant_format"),
                   safe_float(cd.get("avg_carousel_slides")),
                   safe_float(cd.get("posts_with_caption_pct")),
                   safe_float(cd.get("posts_with_location_pct")),
                   safe_float(cd.get("posts_with_usertags_pct")),
                   safe_int(cd.get("avg_caption_length_chars")),
                   safe_int(cd.get("avg_caption_words")),
                   cd.get("caption_style"),
                   safe_date(cd.get("first_post_date")),
                   safe_date(cd.get("last_post_date")),
                   safe_int(cd.get("days_span_scraped")),
                   safe_int(cd.get("days_since_last_post")),
                   cd.get("activity_status"),
                   safe_float(cd.get("avg_days_between_posts")),
                   safe_float(cd.get("estimated_posts_per_week")),
                   safe_float(cd.get("estimated_posts_per_month")),
                   safe_int(cd.get("posting_consistency_score")))])

    # caption_intelligence
    ci = c.get("caption_intelligence") or {}
    batch_insert(cur, tbl("creator_caption_intelligence"),
                 ["creator_id", "posts_with_captions", "languages_detected",
                  "primary_language", "emoji_usage_pct", "avg_hashtags_per_post",
                  "avg_mentions_per_post", "hashtag_strategy", "cta_usage", "uses_cta"],
                 [(creator_id,
                   safe_int(ci.get("posts_with_captions")),
                   j(ci.get("languages_detected")),
                   ci.get("primary_language"),
                   safe_float(ci.get("emoji_usage_pct")),
                   safe_float(ci.get("avg_hashtags_per_post")),
                   safe_float(ci.get("avg_mentions_per_post")),
                   ci.get("hashtag_strategy"),
                   j(ci.get("cta_usage")),
                   bool(ci.get("uses_cta")))])

    # engagement_analytics
    batch_insert(cur, tbl("creator_engagement_analytics"),
                 ["creator_id", "avg_likes", "avg_comments", "avg_er_weighted",
                  "avg_er_simple", "avg_er_top6", "avg_er_last_90_days", "er_grade",
                  "like_comment_ratio", "audience_engagement_type",
                  "total_likes_all_posts", "total_comments_all_posts",
                  "viral_posts_count", "recent_posts_90d"],
                 [(creator_id,
                   safe_int(c.get("avg_likes")),
                   safe_float(c.get("avg_comments")),
                   safe_float(c.get("avg_er_weighted")),
                   safe_float(c.get("avg_er_simple")),
                   safe_float(c.get("avg_er_top6")),
                   safe_float(c.get("avg_er_last_90_days")),
                   c.get("er_grade"),
                   safe_float(c.get("like_comment_ratio")),
                   c.get("audience_engagement_type"),
                   safe_int(c.get("total_likes_all_posts")),
                   safe_int(c.get("total_comments_all_posts")),
                   safe_int(c.get("viral_posts_count"), 0),
                   safe_int(c.get("recent_posts_90d"), 0))])

    # health_scores
    hb = c.get("health_breakdown") or {}
    batch_insert(cur, tbl("creator_health_scores"),
                 ["creator_id", "growth_health_score", "health_grade",
                  "engagement_score", "consistency_score", "collab_score", "viral_score"],
                 [(creator_id,
                   safe_int(c.get("growth_health_score")),
                   c.get("health_grade"),
                   safe_float(hb.get("engagement_score")),
                   safe_float(hb.get("consistency_score")),
                   safe_float(hb.get("collab_score")),
                   safe_float(hb.get("viral_score")))])

    # brand_intelligence
    batch_insert(cur, tbl("creator_brand_intelligence"),
                 ["creator_id", "collaboration_status", "paid_partnership_posts",
                  "ad_tagged_posts", "total_unique_brands", "is_brand_active",
                  "brand_frequency"],
                 [(creator_id,
                   c.get("collaboration_status"),
                   safe_int(c.get("paid_partnership_posts"), 0),
                   safe_int(c.get("ad_tagged_posts"), 0),
                   safe_int(c.get("total_unique_brands"), 0),
                   bool(c.get("is_brand_active")),
                   j(c.get("brand_frequency")))])

    return creator_id


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Insert analyzed.json into PostgreSQL (analyze schema)")
    parser.add_argument("--file",     default=None,      help="Path to analyzed.json")
    parser.add_argument("--schema",   default="analyze", help="PostgreSQL schema name")
    parser.add_argument("--truncate", action="store_true", help="Truncate all tables first")
    args = parser.parse_args()

    global SCHEMA
    SCHEMA = args.schema

    # ── Prompt for file path if not provided ──────────────────────────────────
    file_path = args.file
    if not file_path:
        file_path = input("Enter path to analyzed.json: ").strip()
        if not file_path:
            print("ERROR: No file path provided.")
            sys.exit(1)

    if not os.path.isfile(file_path):
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Unwrap creators list
    if isinstance(data, list):
        creators = data
    elif isinstance(data, dict):
        creators = (data.get("creators") or data.get("data") or
                    data.get("results") or list(data.values())[0])
    else:
        print("ERROR: Unexpected JSON structure.")
        sys.exit(1)

    print(f"Found {len(creators)} creator records. Connecting to database...")

    conn = get_connection()
    conn.autocommit = False
    inserted = updated = failed = 0

    try:
        with conn.cursor() as cur:
            if args.truncate:
                print("Truncating all tables...")
                for child_tbl, _ in POST_CHILD_TABLES:
                    cur.execute(f"TRUNCATE {tbl(child_tbl)} CASCADE")
                cur.execute(f"TRUNCATE {tbl('posts')} CASCADE")
                for child_tbl, _ in CHILD_TABLES_BY_FK:
                    cur.execute(f"TRUNCATE {tbl(child_tbl)} CASCADE")
                cur.execute(f"TRUNCATE {tbl('creators')} CASCADE")
                conn.commit()
                print("Tables truncated.\n")

            for i, creator in enumerate(creators, 1):
                username = creator.get("username", f"<record {i}>")
                try:
                    creator_id = insert_full_creator(cur, creator)
                    conn.commit()
                    inserted += 1
                    print(f"  [{i:4d}/{len(creators)}] ✓  {username:<35}  (id={creator_id})")
                except Exception as e:
                    conn.rollback()
                    failed += 1
                    print(f"  [{i:4d}/{len(creators)}] ✗  {username:<35}  ERROR: {e}")

        print(f"\n{'='*60}")
        print(f"  Done — {inserted} inserted/updated,  {failed} failed")
        print(f"{'='*60}")

    except Exception as e:
        conn.rollback()
        print(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
