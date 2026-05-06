"""Determine creator size category from follower count."""
from __future__ import annotations
from typing import Any, Dict
from ._shapes import user_data


def determine_creator_size(user_info: Dict[str, Any]) -> str:
    fc = user_data(user_info).get("follower_count") or 0
    if not fc:
        return "Unknown"
    if fc < 5000:
        return "Nano-Influencer"
    if fc < 50000:
        return "Micro-Influencer"
    if fc < 500000:
        return "Mid-Tier Influencer"
    if fc < 1000000:
        return "Macro-Influencer"
    return "Mega-Influencer"
