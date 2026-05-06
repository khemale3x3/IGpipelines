"""Extract TikTok / YouTube / Linktree / X links from bio_links."""
from __future__ import annotations
from typing import Any, Dict
from ._shapes import user_data

_PATTERNS = {
    "tiktok": ["tiktok.com", "tiktok.app"],
    "youtube": ["youtube.com", "youtu.be"],
    "linktree": ["linktr.ee"],
    "x": ["twitter.com", "x.com"],
}


def extract_social_links(user_info: Dict[str, Any]) -> Dict[str, Any]:
    u = user_data(user_info)
    bio_links = u.get("bio_links") or []
    out: Dict[str, Any] = {k: None for k in _PATTERNS}
    for link in bio_links:
        if not isinstance(link, dict):
            continue
        url = (link.get("url") or "").lower()
        if not url:
            continue
        for platform, pats in _PATTERNS.items():
            if out[platform] is None and any(p in url for p in pats):
                out[platform] = link.get("url")
    return out
