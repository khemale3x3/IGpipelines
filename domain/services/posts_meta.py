"""Latest-post info + concatenated captions."""
from __future__ import annotations
import datetime as dt
from typing import Any, Dict
from ._shapes import post_edges, caption_text


def get_latest_post_info(post_info: Dict[str, Any]) -> Dict[str, Any]:
    posts = post_edges(post_info)
    if not posts:
        return {"latest_post_date": None, "latest_post_link": None,
                "latest_post_code": None, "days_since_latest": None,
                "latest_post_likes": None, "latest_post_comments": None,
                "latest_post_type": None, "timestamp": None,
                "error": "No posts found"}

    latest_node, latest_ts = None, 0
    for p in posts:
        node = (p or {}).get("node") or {}
        ts = node.get("taken_at") or 0
        if ts > latest_ts:
            latest_ts = ts
            latest_node = node

    if not latest_node or latest_ts == 0:
        return {"latest_post_date": None, "latest_post_link": None,
                "latest_post_code": None, "days_since_latest": None,
                "error": "No valid timestamps"}

    d = dt.datetime.fromtimestamp(latest_ts)
    code = latest_node.get("code", "")
    return {
        "latest_post_date": d.strftime("%Y-%m-%d %H:%M:%S"),
        "latest_post_link": f"https://www.instagram.com/p/{code}" if code else None,
        "latest_post_code": code,
        "days_since_latest": (dt.datetime.now() - d).days,
        "latest_post_likes": latest_node.get("like_count") or 0,
        "latest_post_comments": latest_node.get("comment_count") or 0,
        "latest_post_type": latest_node.get("product_type", "unknown"),
        "timestamp": latest_ts,
        "error": None,
    }


def get_all_captions(post_info: Dict[str, Any]) -> Dict[str, Any]:
    posts = post_edges(post_info)
    captions = []
    for p in posts:
        text = caption_text((p or {}).get("node") or {})
        if text:
            captions.append(text.replace("\n", " ").strip())
    return {"all_posts_caption": " | ".join(captions), "post_count": len(captions),
            "error": None}
