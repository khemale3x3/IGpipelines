"""Creator type / tier / pricing matrix (merged: analyze_insta + finalanalyzer).

Uses the modern tier names from finalanalyzer (Nano/Micro/Macro/Mega) and the
spread-based duration pricing model — but keeps UGC keyword detection across
bio, username, full_name AND captions like analyze_insta does.
"""
from __future__ import annotations
from typing import Any, Dict, List
from ._shapes import user_data, caption_text

_UGC_KEYWORDS = [
    "ugc", "ugccreator", "ugc creator", "user generated content",
    "user-generated content", "content creator", "brand creator",
    "ugc content", "product creator",
]

# (min_price, max_price, roi_range, impressions_single, impressions_range)
PRICING_TIERS = {
    ("UGC Creator", "Beginner"):          (75,    200,   "2×–4×",   "8K",  "8K – 40K"),
    ("UGC Creator", "Experienced"):       (450,   1000,  "4×–8×",   "40K", "40K – 150K"),
    ("Social Media Influencer", "Nano"):  (100,   300,   "5×–10×",  "30K", "30K – 100K"),
    ("Social Media Influencer", "Micro"): (300,   800,   "4×–8×",   "80K", "80K – 400K"),
    ("Social Media Influencer", "Macro"): (2500,  10000, "2.5×–5×", "1M",  "1M – 3M"),
    ("Social Media Influencer", "Mega"):  (10000, 50000, "1.5×–3×", "3M",  "3M – 10M+"),
}


def _classify(user_info: Dict[str, Any], posts: List[Dict[str, Any]]) -> tuple[str, str]:
    u = user_data(user_info)
    fc = u.get("follower_count") or 0
    bag = " ".join([
        (u.get("full_name") or "").lower(),
        (u.get("username") or "").lower(),
        (u.get("biography") or "").lower(),
    ])

    creator_type = "Social Media Influencer"
    if any(k in bag for k in _UGC_KEYWORDS):
        creator_type = "UGC Creator"
    else:
        for p in posts:
            cap = caption_text((p or {}).get("node") or {}).lower()
            if any(k in cap or f"#{k.replace(' ', '')}" in cap for k in _UGC_KEYWORDS):
                creator_type = "UGC Creator"
                break

    if creator_type == "Social Media Influencer" and fc < 1000:
        creator_type, tier = "UGC Creator", "Beginner"
    elif creator_type == "UGC Creator":
        tier = "Beginner" if fc < 1000 else "Experienced"
    else:
        if fc < 10000:
            tier = "Nano"
        elif fc < 50000:
            tier = "Micro"
        elif fc < 500000:
            tier = "Macro"
        else:
            tier = "Mega"
    return creator_type, tier


def extract_creator_pricing(
    user_info: Dict[str, Any], posts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    creator_type, tier = _classify(user_info, posts)

    metrics: Dict[str, Any] = {
        "estimated_roi": "N/A",
        "impressions_visibility": "N/A",
        "expected_impressions_visibility": "N/A",
        "price_usd": "N/A",
        "time_15_seconds": "N/A",
        "time_30_seconds": "N/A",
        "time_60_seconds": "N/A",
        "time_1_to_5_minutes": "N/A",
        "time_greater_than_5_minutes": "N/A",
    }

    key = (creator_type, tier)
    if key in PRICING_TIERS:
        mn, mx, roi, imp_s, imp_r = PRICING_TIERS[key]
        spread = mx - mn
        t15 = mn
        t30 = round(mn + spread * 0.25)
        t60 = round(mn + spread * 0.50)
        t15m = round(mn + spread * 0.75)
        tgt5 = mx
        price_usd = (
            f"TIME_15_SECONDS:{t15}|TIME_30_SECONDS:{t30}|"
            f"TIME_60_SECONDS:{t60}|TIME_1_TO_5_MINUTES:{t15m}|"
            f"TIME_GREATER_THAN_5_MINUTES:{tgt5}"
        )
        metrics = {
            "estimated_roi": roi,
            "impressions_visibility": imp_s,
            "expected_impressions_visibility": imp_r,
            "price_usd": price_usd,
            "time_15_seconds": t15,
            "time_30_seconds": t30,
            "time_60_seconds": t60,
            "time_1_to_5_minutes": t15m,
            "time_greater_than_5_minutes": tgt5,
        }

    return {"creator_type": creator_type, "tier": tier, "creator_pricing_metrics": metrics}
