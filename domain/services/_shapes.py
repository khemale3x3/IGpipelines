"""Helper to safely traverse the Instagram GraphQL JSON shape."""
from __future__ import annotations
from typing import Any, Dict, List

TIMELINE_KEY = "xdt_api__v1__feed__user_timeline_graphql_connection"


def user_data(user_info: Dict[str, Any]) -> Dict[str, Any]:
    return (user_info or {}).get("data", {}).get("user", {}) or {}


def post_edges(post_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    return (
        (post_info or {})
        .get("data", {})
        .get(TIMELINE_KEY, {})
        .get("edges", [])
        or []
    )


def caption_text(node: Dict[str, Any]) -> str:
    cap = node.get("caption") if node else None
    if isinstance(cap, dict):
        return cap.get("text", "") or ""
    return ""
