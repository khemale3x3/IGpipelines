"""Deep location analysis.

Extracts post-level locations and derives city/state/country with multiple
inference layers:

  1. Structured `processed_location` / `location` blocks on each post.
  2. Free-text address parsing using country aliases, US-state abbreviations,
     and a curated set of well-known international cities.
  3. Bio + profile city/zip fallback when posts lack geotags.

The output is intentionally conservative: when we can't be sure we leave
fields as ``None`` rather than guessing.
"""
from __future__ import annotations
import re
from collections import Counter
from typing import Any, Dict, List, Optional

# ---- Reference data ---------------------------------------------------------

_COUNTRIES = {
    "USA": ["USA", "U.S.A", "United States", "U.S.", " US ", "America"],
    "UK": ["UK", "U.K.", "United Kingdom", "England", "Scotland", "Wales",
           "Northern Ireland", "Britain"],
    "Canada": ["Canada", "CAN"],
    "Australia": ["Australia", "AUS"],
    "India": ["India", "Bharat", "IND"],
    "France": ["France", " FR "],
    "Germany": ["Germany", "Deutschland", " DE "],
    "Italy": ["Italy", "Italia", " IT "],
    "Spain": ["Spain", "España", " ES "],
    "Mexico": ["Mexico", "México", " MX "],
    "Brazil": ["Brazil", "Brasil", " BR "],
    "Japan": ["Japan", "日本", " JP "],
    "China": ["China", "中国", " CN "],
    "Nepal": ["Nepal", " NP "],
    "UAE": ["UAE", "United Arab Emirates", "Dubai", "Abu Dhabi"],
    "Singapore": ["Singapore", " SG "],
    "Netherlands": ["Netherlands", "Holland", "Amsterdam"],
    "Ireland": ["Ireland", " IE ", "Dublin"],
}

_US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

# Curated city -> (country, optional state) lookup so that a bare "Paris" or
# "Kathmandu" still yields a country.
_CITY_HINTS: Dict[str, Dict[str, str]] = {
    "new york": {"country": "USA", "state": "New York"},
    "los angeles": {"country": "USA", "state": "California"},
    "san francisco": {"country": "USA", "state": "California"},
    "miami": {"country": "USA", "state": "Florida"},
    "austin": {"country": "USA", "state": "Texas"},
    "chicago": {"country": "USA", "state": "Illinois"},
    "seattle": {"country": "USA", "state": "Washington"},
    "boston": {"country": "USA", "state": "Massachusetts"},
    "london": {"country": "UK"},
    "manchester": {"country": "UK"},
    "edinburgh": {"country": "UK"},
    "paris": {"country": "France"},
    "berlin": {"country": "Germany"},
    "munich": {"country": "Germany"},
    "rome": {"country": "Italy"},
    "milan": {"country": "Italy"},
    "madrid": {"country": "Spain"},
    "barcelona": {"country": "Spain"},
    "tokyo": {"country": "Japan"},
    "osaka": {"country": "Japan"},
    "shanghai": {"country": "China"},
    "beijing": {"country": "China"},
    "mumbai": {"country": "India"},
    "delhi": {"country": "India"},
    "bangalore": {"country": "India"},
    "kathmandu": {"country": "Nepal"},
    "pokhara": {"country": "Nepal"},
    "toronto": {"country": "Canada"},
    "vancouver": {"country": "Canada"},
    "montreal": {"country": "Canada"},
    "sydney": {"country": "Australia"},
    "melbourne": {"country": "Australia"},
    "dubai": {"country": "UAE"},
    "amsterdam": {"country": "Netherlands"},
    "dublin": {"country": "Ireland"},
}

_ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


# ---- Core extraction --------------------------------------------------------

def extract_location_from_posts(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not posts:
        return {
            "primary_location": None, "primary_lat": None, "primary_lng": None,
            "all_locations": [], "location_frequency": {},
            "posts_with_location": 0, "total_posts": 0,
        }

    location_data: List[Dict[str, Any]] = []
    freq: Counter = Counter()
    posts_with_location = 0

    for post in posts:
        node = (post or {}).get("node") or {}
        loc = node.get("processed_location") or node.get("location")
        if not isinstance(loc, dict):
            continue
        name = loc.get("name")
        if not name:
            continue
        posts_with_location += 1
        freq[name] += 1
        lat = loc.get("lat") or loc.get("latitude")
        lng = loc.get("lng") or loc.get("longitude")
        entry = {
            "name": name, "lat": lat, "lng": lng,
            "id": loc.get("id"),
            "address": loc.get("address"),
            "city": loc.get("city"),
            "post_code": node.get("code"),
            "post_link": (
                f"https://www.instagram.com/p/{node.get('code')}"
                if node.get("code") else None
            ),
        }
        if not any(
            l["name"] == name and l["lat"] == lat and l["lng"] == lng
            for l in location_data
        ):
            location_data.append(entry)

    primary, plat, plng = None, None, None
    if freq:
        most_common = freq.most_common(1)[0][0]
        for l in location_data:
            if l["name"] == most_common:
                primary, plat, plng = l["name"], l["lat"], l["lng"]
                break

    return {
        "primary_location": primary,
        "primary_lat": plat,
        "primary_lng": plng,
        "all_locations": location_data,
        "location_frequency": dict(freq),
        "posts_with_location": posts_with_location,
        "total_posts": len(posts),
    }


def parse_address(
    location_name: Optional[str],
    address: Optional[str] = None,
    city: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """Best-effort city/state/country extraction.

    Layers in order: explicit ``city`` arg, structured tokens (state codes,
    country aliases, ZIP), curated city hints, then the leading token of the
    location name as a final guess.
    """
    out: Dict[str, Optional[str]] = {"city": city, "state": None, "country": None}
    if not location_name and not address:
        return out

    combined = " ".join(p for p in [location_name, address] if p).strip()
    cl = combined.lower()
    padded_lower = f" {cl} "
    padded = f" {combined} "

    # 1. Country alias scan (case-insensitive, but state-style abbreviations
    #    stay case-sensitive to avoid grabbing two-letter substrings).
    for country, pats in _COUNTRIES.items():
        for p in pats:
            if p.isupper() and len(p.strip()) <= 3:
                if p in padded or p in f" {combined},":
                    out["country"] = country
                    break
            elif p.lower() in padded_lower:
                out["country"] = country
                break
        if out["country"]:
            break

    # 2. US state detection (abbr or full name). Strong signal => USA.
    if not out["state"]:
        for abbr, full in _US_STATES.items():
            if (
                f" {abbr} " in padded
                or f", {abbr}" in combined
                or f",{abbr}" in combined
                or f" {abbr}," in combined
                or f" {abbr}." in padded
            ):
                out["state"] = full
                out["country"] = "USA"
                break
            if full.lower() in cl:
                out["state"] = full
                out["country"] = "USA"
                break

    # 3. ZIP code => USA hint.
    if not out["country"] and _ZIP_RE.search(combined):
        out["country"] = "USA"

    # 4. City heuristic: prefer first comma-separated token of location name.
    if not out["city"] and location_name:
        first = location_name.split(",")[0].strip()
        if len(first) > 1 and not first.isupper():
            out["city"] = first

    # 5. Curated city hints (fills missing country/state).
    if out["city"]:
        hint = _CITY_HINTS.get(out["city"].lower())
        if hint:
            out["country"] = out["country"] or hint.get("country")
            out["state"] = out["state"] or hint.get("state")

    return out


def infer_location_from_profile(
    bio: Optional[str], city_name: Optional[str], zip_code: Optional[str],
) -> Dict[str, Optional[str]]:
    """Fallback inference using profile-level fields when posts lack geotags."""
    parts = []
    if city_name:
        parts.append(city_name)
    if zip_code:
        parts.append(str(zip_code))
    if bio:
        parts.append(bio)
    if not parts:
        return {"city": None, "state": None, "country": None}
    return parse_address(", ".join(parts), None, city_name)
