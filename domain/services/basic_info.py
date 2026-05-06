"""Basic creator info extraction (merged from analyze_insta + finalanalyzer)."""
from __future__ import annotations
from typing import Any, Dict
from ._shapes import user_data


def extract_basic_info(user_info: Dict[str, Any]) -> Dict[str, Any]:
    u = user_data(user_info)
    username = u.get("username", "") or ""
    return {
        "id": u.get("id", "") or "",
        "account_type": u.get("account_type", "") or "",
        "username": username,
        "follower_count": u.get("follower_count", 0) or 0,
        "following_count": u.get("following_count", 0) or 0,
        "media_count": u.get("media_count", 0) or 0,
        "full_name": u.get("full_name", "") or "",
        "biography": u.get("biography", "") or "",
        "category": u.get("category", "") or "",
        "profile_picture": (
            f"https://assets.veelapp.com/{username}.jpg" if username else ""
        ),
        "is_business": bool(u.get("is_business", False)),
        "is_private": bool(u.get("is_private", False)),
        "is_verified": bool(u.get("is_verified", False)),
        "external_url": u.get("external_url", "") or "",
        "address_street": u.get("address_street", "") or "",
        "city_name": u.get("city_name", "") or "",
        "zip_code": u.get("zip", "") or "",
    }
