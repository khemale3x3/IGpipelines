"""Hashtag + mention extraction from last 90 days."""
from __future__ import annotations
import datetime as dt
import re
from typing import Any, Dict, List
from ._shapes import caption_text

_STOP = {
    "the", "and", "for", "from", "with", "this", "that", "have", "has",
    "her", "his", "our", "my", "your", "their", "its", "as", "at", "by",
    "to", "in", "on", "of", "or", "if",
}


def extract_hashtags_and_mentions(posts: List[Dict[str, Any]], limit: int = 10) -> Dict[str, Any]:
    if not posts:
        return {"hashtags": {}, "mentions": {}, "total_posts_analyzed": 0,
                "date_range": "No posts found"}

    cutoff = int((dt.datetime.now() - dt.timedelta(days=90)).timestamp())
    hcounts: Dict[str, int] = {}
    mcounts: Dict[str, int] = {}
    analyzed = 0

    for p in posts:
        node = (p or {}).get("node") or {}
        if (node.get("taken_at") or 0) < cutoff:
            continue
        analyzed += 1
        text = caption_text(node)
        if not text:
            continue
        for h in re.findall(r"#([A-Za-z0-9_]+)", text):
            hl = h.lower()
            hcounts[hl] = hcounts.get(hl, 0) + 1
        for m in re.findall(r"@([A-Za-z0-9._]+)", text):
            ml = m.lower()
            if len(m) >= 3 and ml not in _STOP:
                mcounts[ml] = mcounts.get(ml, 0) + 1

    today = dt.datetime.now()
    return {
        "hashtags": dict(sorted(hcounts.items(), key=lambda x: x[1], reverse=True)[:limit]),
        "mentions": dict(sorted(mcounts.items(), key=lambda x: x[1], reverse=True)[:limit]),
        "total_posts_analyzed": analyzed,
        "date_range": (
            f"{(today - dt.timedelta(days=90)).strftime('%Y-%m-%d')} to "
            f"{today.strftime('%Y-%m-%d')}"
        ),
    }
