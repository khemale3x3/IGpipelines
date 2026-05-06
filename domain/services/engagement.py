"""Top-6 posts engagement rate over last 90 days."""
from __future__ import annotations
import datetime as dt
from typing import Any, Dict, List, Tuple, Optional
from ._shapes import post_edges, user_data


def calculate_top_post_er(
    user_info: Dict[str, Any], post_info: Dict[str, Any]
) -> Tuple[Optional[int], Optional[List[Dict[str, Any]]], Optional[float]]:
    followers = user_data(user_info).get("follower_count") or 0
    if followers == 0:
        return 0, [], 0.0

    cutoff = int((dt.datetime.now() - dt.timedelta(days=90)).timestamp())
    recent_scores: List[Dict[str, Any]] = []
    total_recent = 0

    for edge in post_edges(post_info):
        node = edge.get("node") or {}
        ts = node.get("taken_at") or 0
        if ts < cutoff:
            continue
        total_recent += 1
        likes = node.get("like_count") or 0
        comments = node.get("comment_count") or 0
        score = likes + 5 * comments
        er = (score / followers) * 100 if followers else 0
        recent_scores.append({
            "interaction_score": score,
            "likes": likes,
            "comments": comments,
            "engagement_rate": round(er, 2),
            "post_code": node.get("code", ""),
            "taken_at": dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
        })

    if not recent_scores:
        return None, None, None

    top = sorted(recent_scores, key=lambda p: p["interaction_score"], reverse=True)[:6]
    avg = round(sum(p["engagement_rate"] for p in top) / len(top), 2) if top else 0.0
    return total_recent, top, avg
