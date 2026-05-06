import os
import sys
import json
import datetime
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from colorama import init, Fore, Style
import csv
import random
from collections import Counter

# Initialize colorama
init(autoreset=True)

# The full analyzer implementation mirrors the richer analyzer in tools/finalanalyzer.py

def load_json_file(file_path: str) -> dict:
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception as e:
        print(f"{Fore.RED}Error loading JSON file {file_path}: {str(e)}{Style.RESET_ALL}")
        return {}
        return {}


    def _format_impressions_abbrev(value) -> str:
        """Format an integer or numeric string into K/M shorthand (e.g., 30000 -> '30K')."""
        try:
            if value is None:
                return 'N/A'
            if isinstance(value, str):
                s = value.strip().upper().replace(',', '')
                if s.endswith('K') or s.endswith('M'):
                    return s
                # try to parse numeric string
                value = int(float(s))
            val = int(value)
            if val >= 1_000_000:
                m = val / 1_000_000
                # show one decimal if not integer
                return f"{m:.1f}M" if not m.is_integer() else f"{int(m)}M"
            if val >= 1_000:
                k = val / 1_000
                return f"{k:.1f}K" if not k.is_integer() else f"{int(k)}K"
            return str(val)
        except Exception:
            return str(value)

# Keep a module-level set of generated impressions to reduce duplicates
_generated_impressions = set()

def _parse_impressions_range(range_str: str) -> Tuple[int, int]:
    """Parse human-readable range like '8K – 40K' or '1M – 3M' into integer min/max."""
    if not range_str or not isinstance(range_str, str):
        return 0, 0
    try:
        parts = re.split(r'–|-', range_str)
        if len(parts) != 2:
            return 0, 0
        def conv(part: str) -> int:
            s = part.strip().upper().replace(',', '')
            if s.endswith('K'):
                return int(float(s[:-1]) * 1_000)
            if s.endswith('M'):
                return int(float(s[:-1]) * 1_000_000)
            return int(float(s))
        return conv(parts[0]), conv(parts[1])
    except Exception:
        return 0, 0

def _generate_unique_impression(min_val: int, max_val: int, seen: set, attempts: int = 10) -> int:
    """Generate a random impression value within range, try to avoid collisions."""
    if min_val <= 0 or max_val <= 0 or min_val > max_val:
        return 0
    for _ in range(attempts):
        # sample and round to nearest 100 to keep numbers realistic
        v = random.randint(min_val, max_val)
        v = int(round(v / 100.0) * 100)
        if v not in seen:
            seen.add(v)
            return v
    # fallback: perturb by adding a small incremental offset
    base = random.randint(min_val, max_val)
    offset = 1
    while base + offset in seen and offset < 10000:
        offset += 1
    val = base + offset
    seen.add(val)
    return val


def extract_location_from_posts(posts: List[dict]) -> Dict:
    if not posts:
        return {
            'primary_location': None,
            'primary_lat': None,
            'primary_lng': None,
            'all_locations': [],
            'location_frequency': {},
            'posts_with_location': 0,
            'total_posts': 0
        }

    location_data = []
    location_frequency = Counter()
    posts_with_location = 0

    for post in posts:
        try:
            if not post or not isinstance(post, dict):
                continue

            node = post.get('node', {})
            if not node:
                continue

            location = node.get('processed_location') or node.get('location')

            if location and isinstance(location, dict):
                location_name = location.get('name')
                lat = location.get('lat') or location.get('latitude')
                lng = location.get('lng') or location.get('longitude')
                location_id = location.get('id')

                if location_name:
                    posts_with_location += 1
                    location_frequency[location_name] += 1

                    location_entry = {
                        'name': location_name,
                        'lat': lat,
                        'lng': lng,
                        'id': location_id,
                        'address': location.get('address'),
                        'city': location.get('city'),
                        'post_code': node.get('code'),
                        'post_link': f"https://www.instagram.com/p/{node.get('code')}" if node.get('code') else None
                    }

                    if not any(loc['name'] == location_name and loc['lat'] == lat and loc['lng'] == lng for loc in location_data):
                        location_data.append(location_entry)

        except (AttributeError, TypeError, KeyError):
            continue

    primary_location = None
    primary_lat = None
    primary_lng = None

    if location_frequency:
        most_common_location = location_frequency.most_common(1)[0][0]
        for loc in location_data:
            if loc['name'] == most_common_location:
                primary_location = loc['name']
                primary_lat = loc.get('lat')
                primary_lng = loc.get('lng')
                break

    return {
        'primary_location': primary_location,
        'primary_lat': primary_lat,
        'primary_lng': primary_lng,
        'all_locations': location_data,
        'location_frequency': dict(location_frequency),
        'posts_with_location': posts_with_location,
        'total_posts': len(posts)
    }

def parse_location_to_address_components(location_name: str, address: str = None, city: str = None) -> Dict:
    result = {'city': None, 'state': None, 'country': None}
    if not location_name:
        return result
    if city:
        result['city'] = city

    country_patterns = {
        'USA': ['USA', 'United States', 'US', 'America'],
        'UK': ['UK', 'United Kingdom', 'England', 'Scotland', 'Wales'],
        'Canada': ['Canada', 'CAN'],
        'Australia': ['Australia', 'AUS'],
        'India': ['India', 'IND'],
        'France': ['France', 'FR'],
        'Germany': ['Germany', 'DE'],
        'Italy': ['Italy', 'IT'],
        'Spain': ['Spain', 'ES'],
        'Mexico': ['Mexico', 'MX'],
        'Brazil': ['Brazil', 'BR'],
        'Japan': ['Japan', 'JP'],
        'China': ['China', 'CN'],
        'Nepal': ['Nepal', 'NP', 'Kathmandu'],
    }

    us_states = {
        'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas', 'CA': 'California',
        'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware', 'FL': 'Florida', 'GA': 'Georgia',
        'HI': 'Hawaii', 'ID': 'Idaho', 'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa',
        'KS': 'Kansas', 'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
        'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
        'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire',
        'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina',
        'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma', 'OR': 'Oregon', 'PA': 'Pennsylvania',
        'RI': 'Rhode Island', 'SC': 'South Carolina', 'SD': 'South Dakota', 'TN': 'Tennessee',
        'TX': 'Texas', 'UT': 'Utah', 'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington',
        'WV': 'West Virginia', 'WI': 'Wisconsin', 'WY': 'Wyoming'
    }

    combined_text = f"{location_name} {address or ''}"

    for country, patterns in country_patterns.items():
        for pattern in patterns:
            if pattern.lower() in combined_text.lower():
                result['country'] = country
                break
        if result['country']:
            break

    if result['country'] == 'USA' or not result['country']:
        for abbr, full_name in us_states.items():
            if f" {abbr} " in f" {combined_text} " or f",{abbr}," in combined_text:
                result['state'] = full_name
                result['country'] = 'USA'
                break
            elif full_name.lower() in combined_text.lower():
                result['state'] = full_name
                result['country'] = 'USA'
                break

    if not result['city']:
        parts = location_name.split(',')
        if len(parts) > 0:
            potential_city = parts[0].strip()
            if len(potential_city) > 2 and potential_city[0].isupper():
                result['city'] = potential_city

    return result

def extract_basic_info(user_info: dict) -> dict:
    user_data = user_info.get('data', {}).get('user', {})
    username = user_data.get('username', '')
    follower_count = user_data.get('follower_count', '')
    full_name = user_data.get('full_name', '')
    biography = user_data.get('biography', '')
    category = user_data.get('category', '')
    profile_picture = f"https://assets.veelapp.com/{username}.jpg" if username != '' else ''

    # try to surface a primary key from user info (pk/id)
    pk = user_data.get('pk') or user_data.get('id') or user_data.get('user_id')

    return {
        'username': username,
        'follower_count': follower_count,
        'full_name': full_name,
        'biography': biography,
        'profile_picture': profile_picture,
        'category': category,
        'pk': pk
    }

def identify_gender(user_info: dict) -> str:
    user_data = user_info.get('data', {}).get('user', {})

    pronouns = user_data.get('pronouns', [])
    if pronouns and isinstance(pronouns, list):
        for pronoun_obj in pronouns:
            if isinstance(pronoun_obj, dict):
                pronoun_text = pronoun_obj.get('pronoun', '').lower().strip()
                if pronoun_text:
                    if pronoun_text in ['she/her', 'she', 'her']:
                        return 'Female'
                    elif pronoun_text in ['he/him', 'he', 'him']:
                        return 'Male'
                    elif pronoun_text in ['they/them', 'they', 'them', 'ze/zir', 'xe/xem', 'it/its']:
                        return 'Non-binary'
            elif isinstance(pronoun_obj, str):
                pronoun_text = pronoun_obj.lower().strip()
                if pronoun_text in ['she/her', 'she', 'her']:
                    return 'Female'
                elif pronoun_text in ['he/him', 'he', 'him']:
                    return 'Male'
                elif pronoun_text in ['they/them', 'they', 'them', 'ze/zir', 'xe/xem', 'it/its']:
                    return 'Non-binary'

    biography = user_data.get('biography', '').lower() if user_data.get('biography') else ''
    full_name = user_data.get('full_name', '').lower() if user_data.get('full_name') else ''
    username = user_data.get('username', '').lower() if user_data.get('username') else ''

    all_text = f"{biography} {full_name} {username}"

    female_indicators = [
        'she/her', 'she', 'her', 'woman', 'girl', 'female', 'lady', 'mom', 'mother',
        'wife', 'daughter', 'sister', 'girlfriend', 'actress', 'queen', 'princess',
        'mama', 'mum', 'mummy', 'mommy', 'mrs', 'ms', 'miss'
    ]

    male_indicators = [
        'he/him', 'he', 'him', 'man', 'boy', 'male', 'guy', 'dad', 'father',
        'husband', 'son', 'brother', 'boyfriend', 'actor', 'king', 'prince',
        'papa', 'daddy', 'mr'
    ]

    non_binary_indicators = [
        'they/them', 'them', 'they', 'non-binary', 'nonbinary', 'nb', 'enby',
        'genderfluid', 'genderqueer', 'agender', 'ze/zir', 'xe/xem'
    ]

    female_score = sum(1 for indicator in female_indicators if indicator in all_text)
    male_score = sum(1 for indicator in male_indicators if indicator in all_text)
    non_binary_score = sum(1 for indicator in non_binary_indicators if indicator in all_text)

    max_score = max(female_score, male_score, non_binary_score)
    if max_score == 0:
        return 'Unknown'
    elif female_score == max_score:
        return 'Female'
    elif male_score == max_score:
        return 'Male'
    else:
        return 'Non-binary'

def extract_social_links(user_info: dict) -> dict:
    user_data = user_info.get('data', {}).get('user', {})
    bio_links = user_data.get('bio_links', [])

    extracted_links = {'tiktok': None, 'youtube': None, 'linktree': None, 'x': None}

    platform_patterns = {
        'tiktok': ['tiktok.com', 'tiktok.app'],
        'youtube': ['youtube.com', 'youtu.be'],
        'linktree': ['linktr.ee'],
        'x': ['twitter', '/x.com']
    }

    for link_obj in bio_links:
        if not isinstance(link_obj, dict):
            continue
        url = link_obj.get('url', '')
        if not url:
            continue
        url_lower = url.lower()
        for platform, patterns in platform_patterns.items():
            for pattern in patterns:
                if pattern in url_lower and extracted_links[platform] is None:
                    extracted_links[platform] = url
                    break

    return extracted_links

def extract_other_urls(user_info: dict) -> List[str]:
    """Return any other urls present in bio_links that aren't mapped to known platforms."""
    user_data = user_info.get('data', {}).get('user', {})
    bio_links = user_data.get('bio_links', [])
    other = []
    known_patterns = ['tiktok.com', 'tiktok.app', 'youtube.com', 'youtu.be', 'linktr.ee', 'twitter', 'x.com']
    for link_obj in bio_links:
        if not isinstance(link_obj, dict):
            continue
        url = link_obj.get('url', '')
        if not url:
            continue
        if not any(pat in url.lower() for pat in known_patterns):
            other.append(url)
    return other

def extract_creator_pricing(user_info: dict, posts: List[dict]) -> dict:
    ugc_keywords = ['ugc', 'ugccreator', 'ugc creator', 'user generated content', 'user-generated content']
    user_data = user_info.get('data', {}).get('user', {})
    username = user_data.get('username', '').lower()
    fullname = user_data.get('full_name', '').lower()
    biography = user_data.get('biography', '').lower()
    follower_count = user_data.get('follower_count', 0)

    creator_type = "Social Media Influencer"
    for text in [fullname, username, biography]:
        if any(keyword in text for keyword in ugc_keywords):
            creator_type = "UGC Creator"
            break

    if creator_type != "UGC Creator":
        for post in posts:
            try:
                caption_text = post.get('node', {}).get('caption', {}).get('text', '')
                caption_lower = caption_text.lower()
                if any(keyword in caption_lower or f'#{keyword.replace(" ", "")}' in caption_lower for keyword in ugc_keywords):
                    creator_type = "UGC Creator"
                    break
            except (AttributeError, TypeError, KeyError):
                continue

    tier = "Unknown"
    if creator_type == "Social Media Influencer" and follower_count < 1000:
        creator_type = "UGC Creator"
        tier = "Beginner"
    elif creator_type == "UGC Creator":
        tier = "Beginner" if follower_count < 1000 else "Experienced"
    elif creator_type == "Social Media Influencer":
        if follower_count < 10000:
            tier = "Nano"
        elif follower_count < 50000:
            tier = "Micro"
        elif follower_count < 500000:
            tier = "Macro"
        else:
            tier = "Mega"

    creator_pricing_metrics = {
        'estimated_roi': 'N/A',
        'impressions_visibility': 'N/A',
        'expected_impressions_visibility': 'N/A',
        'price_usd': 'N/A',
        'time_15_seconds': 'N/A',
        'time_30_seconds': 'N/A',
        'time_60_seconds': 'N/A',
        'time_1_to_5_minutes': 'N/A',
        'time_greater_than_5_minutes': 'N/A'
    }

    pricing_tiers = {
        ("UGC Creator", "Beginner"):          (75,    200,   "2×–4×",   "8K",  "8K – 40K"),
        ("UGC Creator", "Experienced"):       (450,   1000,  "4×–8×",   "40K", "40K – 150K"),
        ("Social Media Influencer", "Nano"):  (100,   300,   "5×–10×",  "30K", "30K – 100K"),
        ("Social Media Influencer", "Micro"): (300,   800,   "4×–8×",   "80K", "80K – 400K"),
        ("Social Media Influencer", "Macro"): (2500,  10000, "2.5×–5×", "1M",  "1M – 3M"),
        ("Social Media Influencer", "Mega"):  (10000, 50000, "1.5×–3×", "3M",  "3M – 10M+"),
    }

    base_price_key = (creator_type, tier)
    if base_price_key in pricing_tiers:
        min_price, max_price, roi, impressions_single, impressions_range = pricing_tiers[base_price_key]
        spread = max_price - min_price
        t15   = min_price
        t30   = round(min_price + spread * 0.25)
        t60   = round(min_price + spread * 0.50)
        t1to5 = round(min_price + spread * 0.75)
        tgt5  = max_price

        price_usd = (
            f"TIME_15_SECONDS:{t15}|"
            f"TIME_30_SECONDS:{t30}|"
            f"TIME_60_SECONDS:{t60}|"
            f"TIME_1_TO_5_MINUTES:{t1to5}|"
            f"TIME_GREATER_THAN_5_MINUTES:{tgt5}"
        )

        # generate a unique random impressions visibility within the numeric range
        min_imp, max_imp = _parse_impressions_range(impressions_range)
        if min_imp == 0 and max_imp == 0:
            # try to parse single shorthand (e.g., '80K' or '1M')
            s = impressions_single.upper().replace(',', '').strip()
            if s.endswith('K'):
                min_imp = max_imp = int(float(s[:-1]) * 1_000)
            elif s.endswith('M'):
                min_imp = max_imp = int(float(s[:-1]) * 1_000_000)
            else:
                try:
                    min_imp = max_imp = int(float(s))
                except Exception:
                    min_imp = 0

        impressions_value = _generate_unique_impression(min_imp, max_imp, _generated_impressions) if min_imp and max_imp else 0
        # Format impressions as K/M shorthand — use a local formatter to avoid globals issues
        def _local_fmt(v):
            try:
                if v is None:
                    return 'N/A'
                if isinstance(v, str):
                    s = v.strip().upper().replace(',', '')
                    if s.endswith('K') or s.endswith('M'):
                        return s
                    v = int(float(s))
                val = int(v)
                if val >= 1_000_000:
                    m = val / 1_000_000
                    return f"{m:.1f}M" if not m.is_integer() else f"{int(m)}M"
                if val >= 1_000:
                    k = val / 1_000
                    return f"{k:.1f}K" if not k.is_integer() else f"{int(k)}K"
                return str(val)
            except Exception:
                return str(v)

        impressions_formatted = _local_fmt(impressions_value) if impressions_value else _local_fmt(impressions_single)

        creator_pricing_metrics = {
            'estimated_roi': roi,
            'impressions_visibility': impressions_formatted,
            'expected_impressions_visibility': impressions_range,
            'price_usd': price_usd,
            'time_15_seconds': t15,
            'time_30_seconds': t30,
            'time_60_seconds': t60,
            'time_1_to_5_minutes': t1to5,
            'time_greater_than_5_minutes': tgt5
        }

    return {'creator_type': creator_type, 'tier': tier, 'creator_pricing_metrics': creator_pricing_metrics}

def identify_niche(user_info: dict) -> dict:
    niche_categories = {
        "Fashion & Beauty": [
            "fashion", "style", "outfit", "clothing", "model", "dress", "accessories",
            "fashionista", "ootd", "stylist", "boutique", "wardrobe", "trend", "chic",
            "makeup", "skincare", "beauty", "cosmetics", "haircare", "nails", "glam",
            "makeupartist", "beautician", "mua", "beautyblogger", "makeover", "cosmetic",
            "skincareroutine", "lashes", "aesthetic", "hairstyle", "grwm", "luxury"
        ],
        "Lifestyle": [
            "lifestyle", "life", "daily", "routine", "inspiration", "motivation",
            "blogger", "lifestyleblogger", "living", "vibes", "mindful",
            "selfcare", "selflove", "positivity", "hustle", "grind",
            "entertainment", "movie", "film", "tv", "television", "cinema", "streaming",
            "comedy", "funny", "humor", "laugh", "joke", "prank", "comedian", "meme",
            "music", "musician", "song", "singer", "band", "concert",
            "dance", "dancer", "choreography", "viral", "trending", "vlog", "vlogger"
        ],
        "Gaming & eSports": [
            "gaming", "gamer", "videogames", "game", "esports", "playstation", "xbox",
            "nintendo", "streamer", "twitch", "console", "pc", "mobile", "rpg",
            "fps", "mmorpg", "gamingsetup", "gamedev", "minecraft", "fortnite",
            "pubg", "valorant", "lol", "leagueoflegends", "gamestreamer"
        ],
        "Food & Cooking": [
            "food", "cooking", "recipe", "chef", "foodie", "cuisine", "baking",
            "delicious", "yummy", "foodblogger", "culinary", "restaurant", "eats",
            "tasty", "kitchen", "homecook", "bbq", "vegan", "foodphotography",
            "healthyfood", "meal", "dessert", "pastry", "baker", "instafood",
            "foodlover", "nutrition", "plantbased", "vegetarian"
        ],
        "Fitness & Wellness": [
            "fitness", "workout", "gym", "exercise", "health", "training", "muscle",
            "fit", "fitnessmotivation", "trainer", "bodybuilding", "crossfit", "yoga",
            "pilates", "running", "weightloss", "gains", "cardio", "strength",
            "wellness", "mindfulness", "meditation", "nutritionist", "dietitian",
            "wellbeing", "mental", "holistic", "athleticism", "sportsmotivation"
        ],
        "Education / Skill": [
            "education", "learning", "school", "knowledge", "teach", "study", "student",
            "lesson", "teacher", "tutor", "academic", "university", "college", "learn",
            "tutorial", "howto", "tips", "skills", "development", "coaching",
            "onlinecourse", "elearning", "productivity", "career", "professional",
            "selfimprovement", "growth", "language", "science", "history"
        ],
        "Travel": [
            "travel", "wanderlust", "adventure", "explore", "tourism", "vacation",
            "trip", "journey", "destination", "traveler", "backpacker", "nomad",
            "wanderer", "explorer", "digitalnomad", "roadtrip", "travelgram",
            "worldtravel", "bucketlist", "hiking", "camping", "solotravel",
            "travellife", "travelphotography", "hotel", "resort", "beach"
        ],
        "Tech & Gadgets": [
            "technology", "tech", "gadget", "device", "software", "app", "smartphone",
            "computer", "digital", "innovation", "startup", "coding", "developer",
            "geek", "ai", "cybersecurity", "programming", "iot", "review",
            "unboxing", "techreview", "apple", "android", "saas", "machinelearning",
            "datascience", "robotics", "wearables", "smartwatch"
        ],
        "Personal Finance": [
            "finance", "investing", "stocks", "cryptocurrency", "money", "financial",
            "wealth", "investor", "trader", "bitcoin", "crypto", "forex", "portfolio",
            "business", "entrepreneur", "marketing", "startup", "success", "ceo",
            "founder", "corporate", "leadership", "boss", "realestate",
            "passiveincome", "budgeting", "savings", "frugal", "sidehustle",
            "stockmarket", "dividends", "financialfreedom", "moneytips"
        ],
        "Art / DIY": [
            "art", "artist", "drawing", "painting", "creative", "design", "illustration",
            "designer", "painter", "sculptor", "gallery", "artwork", "canvas",
            "diy", "handmade", "craft", "crafting", "upcycle", "homedecor",
            "interiordesign", "photography", "digitalart", "graffiti",
            "sketch", "watercolor", "calligraphy", "pottery", "woodwork"
        ],
        "Pets & Animals": [
            "pets", "dog", "cat", "animal", "puppy", "kitten", "wildlife",
            "veterinarian", "petcare", "rescue", "adoption", "dogtrainer",
            "animallover", "petsofinstagram", "dogsofinstagram", "catsofinstagram",
            "exoticpets", "birdwatching", "nature", "conservation",
            "petowner", "furbaby", "doglife", "catlife", "reptile"
        ],
        "Family & Parenting": [
            "family", "parenting", "mom", "dad", "children", "kids", "baby",
            "mother", "father", "parent", "motherhood", "fatherhood", "toddler",
            "newborn", "pregnancy", "momlife", "dadlife", "parentingtips",
            "familytime", "homeschool", "siblings", "grandparent",
            "familyfirst", "raisingkids", "mommy", "daddy", "blessed"
        ],
        "Others": []
    }

    user_data = user_info.get('data', {}).get('user', {})
    biography = user_data.get('biography', '') or ''
    username = user_data.get('username', '') or ''
    full_name = user_data.get('full_name', '') or ''

    all_text_sources = {'biography': biography, 'username': username, 'full_name': full_name}

    keyword_to_categories = {}
    for category, keywords in niche_categories.items():
        for kw in keywords:
            keyword_to_categories.setdefault(kw, []).append(category)

    all_matched_keywords = []
    keyword_sources = {}
    total_keyword_counts = {}

    for source_name, text in all_text_sources.items():
        if not text:
            continue
        if source_name == 'username':
            clean_text = text.strip('_').replace('_', ' ').replace('.', ' ')
            words = [w.strip().lower() for w in clean_text.split() if w and len(w) > 1]
        else:
            words = [w.strip().lower() for w in text.replace(',', ' ').replace('\n', ' ').split() if w]

        for word in words:
            if word in keyword_to_categories:
                all_matched_keywords.append(word)
                keyword_sources.setdefault(word, []).append(source_name)
                total_keyword_counts[word] = total_keyword_counts.get(word, 0) + 1

    source_weights = {'username': 2.0, 'full_name': 1.0, 'biography': 1.5}

    scoreable = {k: v for k, v in niche_categories.items() if k != "Others"}
    niche_scores = {category: 0.0 for category in scoreable}

    for keyword, count in total_keyword_counts.items():
        for category in keyword_to_categories.get(keyword, []):
            if category == "Others":
                continue
            weighted_score = sum(source_weights.get(src, 1.0) for src in keyword_sources[keyword])
            niche_scores[category] += weighted_score * count

    total_score = sum(niche_scores.values()) or 0
    sorted_niches = sorted(niche_scores.items(), key=lambda x: x[1], reverse=True)

    if total_score == 0:
        overall_niche = "Others"
        distribution = {"Others": 100.0}
    else:
        distribution = {cat: round(score / total_score * 100, 1) for cat, score in niche_scores.items() if score > 0 and round(score / total_score * 100, 1) >= 2}
        overall_niche = sorted_niches[0][0] if sorted_niches[0][1] > 0 else "Others"

    return {"overall_niche": overall_niche, "distribution": distribution, "matched_keywords": all_matched_keywords}

def extract_ugc_examples(posts: List[dict]) -> str:
    if not posts:
        return ""
    ugc_codes = []
    uname = None
    try:
        if posts and len(posts) > 0:
            first_post = posts[0]
            if first_post and isinstance(first_post, dict):
                node = first_post.get("node", {})
                if node:
                    user_data = node.get("user", {})
                    if user_data:
                        uname = user_data.get("username")
    except (AttributeError, TypeError, IndexError):
        pass

    for post in posts:
        try:
            if not post or not isinstance(post, dict):
                continue
            node = post.get('node', {})
            if not node:
                continue
            if node.get('product_type') != 'clips':
                continue
            if node.get('is_paid_partnership') is True:
                code = node.get('code')
                if code and len(ugc_codes) < 3:
                    ugc_codes.append(code)
        except (AttributeError, TypeError, KeyError):
            continue

    if len(ugc_codes) < 3:
        for post in posts:
            try:
                if not post or not isinstance(post, dict):
                    continue
                node = post.get('node', {})
                if not node:
                    continue
                if node.get('product_type') != 'clips':
                    continue
                caption_obj = node.get('caption')
                caption = ''
                if caption_obj and isinstance(caption_obj, dict):
                    caption = caption_obj.get('text', '') or ''
                if caption and isinstance(caption, str):
                    caption_lower = caption.lower()
                    if '#ad' in caption_lower or '#collab' in caption_lower:
                        code = node.get('code')
                        if code and code not in ugc_codes and len(ugc_codes) < 3:
                            ugc_codes.append(code)
            except (AttributeError, TypeError, KeyError):
                continue

    if ugc_codes:
        urls = [f"https://www.instagram.com/p/{code}" for code in ugc_codes]
        return " | ".join(urls)
    return ""

def identify_collaborations(posts: List[dict]) -> Dict:
    if not posts:
        return {'status': None, 'total_collaborations': 0, 'recent_collaborations': 0, 'all_collaborations': [], 'ugc_examples': ""}
    uname = None
    try:
        if posts and len(posts) > 0:
            first_post = posts[0]
            if first_post and isinstance(first_post, dict):
                node = first_post.get("node", {})
                if node:
                    user_data = node.get("user", {})
                    if user_data:
                        uname = user_data.get("username")
    except (AttributeError, TypeError, IndexError):
        pass

    final_status = None
    all_collabs = []
    recent_brands = []
    recent_threshold = 300
    today = datetime.datetime.now()
    recent_cutoff = today - datetime.timedelta(days=recent_threshold)
    seen_collabs = set()

    for post in posts:
        try:
            if not post or not isinstance(post, dict):
                continue
            node = post.get('node', {})
            if not node:
                continue
            if node.get('is_paid_partnership') is True:
                final_status = "Active"
                caption_obj = node.get('caption')
                caption = ''
                if caption_obj and isinstance(caption_obj, dict):
                    caption = caption_obj.get('text', '') or ''

                taken_at = node.get('taken_at')
                is_recent = False
                if taken_at:
                    try:
                        post_date = datetime.datetime.fromtimestamp(taken_at)
                        is_recent = post_date > recent_cutoff
                    except (ValueError, TypeError):
                        pass

                if caption and isinstance(caption, str):
                    mentions = re.findall(r'@([A-Za-z0-9._]+)', caption)
                    for mention in mentions:
                        brand_name = mention.rstrip('.')
                        if len(brand_name) < 3 or brand_name.lower() in ['the', 'and', 'for', 'from', 'with', 'this', 'that', 'have', 'has', 'her', 'his', 'our', 'my', 'your', 'their', 'its', 'as', 'at', 'by', 'to', 'in', 'on', 'of', 'or', 'if']:
                            continue
                        if brand_name not in seen_collabs:
                            all_collabs.append({'name': brand_name, 'count': 1, 'is_recent': is_recent, 'source': 'paid_partnership'})
                            seen_collabs.add(brand_name)
                            if is_recent:
                                recent_brands.append({'name': brand_name, 'source': 'mention'})
                break
        except (AttributeError, TypeError, KeyError):
            continue

    for post in posts:
        try:
            if not post or not isinstance(post, dict):
                continue
            node = post.get('node', {})
            if not node:
                continue
            taken_at = node.get('taken_at')
            is_recent = False
            if taken_at:
                try:
                    post_date = datetime.datetime.fromtimestamp(taken_at)
                    is_recent = post_date > recent_cutoff
                except (ValueError, TypeError):
                    pass

            owner = node.get('owner', {})
            if owner and isinstance(owner, dict):
                post_owner_username = owner.get('username')
                if post_owner_username and post_owner_username != uname and post_owner_username not in seen_collabs:
                    all_collabs.append({'name': post_owner_username, 'count': 1, 'is_recent': is_recent, 'source': 'owner'})
                    seen_collabs.add(post_owner_username)
                    if is_recent:
                        recent_brands.append({'name': post_owner_username, 'source': 'owner'})

            coauthor_producers = node.get('coauthor_producers')
            if coauthor_producers and isinstance(coauthor_producers, list):
                for coauthor in coauthor_producers:
                    if coauthor and isinstance(coauthor, dict):
                        coauthor_username = coauthor.get("username")
                        if coauthor_username and coauthor_username != uname and coauthor_username not in seen_collabs:
                            all_collabs.append({'name': coauthor_username, 'count': 1, 'is_recent': is_recent, 'source': 'coauthor'})
                            seen_collabs.add(coauthor_username)
                            if is_recent:
                                recent_brands.append({'name': coauthor_username, 'source': 'coauthor'})
        except (AttributeError, TypeError, KeyError):
            continue

    if final_status is None:
        status_hashtags = ['ad', 'collab']
        for post in posts:
            try:
                if not post or not isinstance(post, dict):
                    continue
                node = post.get('node', {})
                if not node:
                    continue
                caption_obj = node.get('caption')
                caption = ''
                if caption_obj and isinstance(caption_obj, dict):
                    caption = caption_obj.get('text', '') or ''

                taken_at = node.get('taken_at')
                is_recent = False
                if taken_at:
                    try:
                        post_date = datetime.datetime.fromtimestamp(taken_at)
                        is_recent = post_date > recent_cutoff
                    except (ValueError, TypeError):
                        pass

                if caption and isinstance(caption, str):
                    caption_lower = caption.lower()
                    for tag in status_hashtags:
                        if f'#{tag}' in caption_lower:
                            final_status = "Active"
                            mentions = re.findall(r'@([A-Za-z0-9._]+)', caption)
                            for mention in mentions:
                                brand_name = mention.rstrip('.')
                                if len(brand_name) < 3 or brand_name.lower() in ['the', 'and', 'for', 'from', 'with', 'this', 'that', 'have', 'has', 'her', 'his', 'our', 'my', 'your', 'their', 'its', 'as', 'at', 'by', 'to', 'in', 'on', 'of', 'or', 'if']:
                                    continue
                                if brand_name not in seen_collabs:
                                    all_collabs.append({'name': brand_name, 'count': 1, 'is_recent': is_recent, 'source': 'tag'})
                                    seen_collabs.add(brand_name)
                                    if is_recent:
                                        recent_brands.append({'name': brand_name, 'source': 'mention'})
                            break
                if final_status == "Active":
                    break
            except (AttributeError, TypeError, KeyError):
                continue

    ugc_examples = extract_ugc_examples(posts)

    collaboration_info = {'status': final_status, 'total_collaborations': len(all_collabs), 'recent_collaborations': len(recent_brands), 'all_collaborations': all_collabs, 'ugc_examples': ugc_examples}
    return collaboration_info

def calculate_top_post_er(post_info: dict, user_info: dict) -> tuple:
    followers = user_info.get('data', {}).get('user', {}).get('follower_count', 0)
    if followers == 0:
        return 0, [], 0
    three_months_ago = datetime.datetime.now() - datetime.timedelta(days=90)
    three_months_ago_unix = int(three_months_ago.timestamp())
    all_posts = post_info.get('data', {}).get('xdt_api__v1__feed__user_timeline_graphql_connection', {}).get('edges', [])
    recent_posts_with_scores = []
    total_last_three_months_posts = 0
    for post in all_posts:
        node = post.get('node', {})
        post_time = node.get('taken_at', 0)
        if post_time >= three_months_ago_unix:
            total_last_three_months_posts += 1
            likes = node.get('like_count', 0)
            comments = node.get('comment_count', 0)
            interaction_score = likes + (5 * comments)
            individual_er = ((likes + (5 * comments)) / followers) * 100
            media_type = node.get('media_type') or node.get('__typename') or None
            accessibility_caption = node.get('accessibility_caption') or node.get('accessibility_caption_text') or None
            recent_posts_with_scores.append({
                'interaction_score': interaction_score,
                'likes': likes,
                'comments': comments,
                'engagement_rate': round(individual_er, 2),
                'post_code': node.get('code', ''),
                'taken_at': datetime.datetime.fromtimestamp(post_time).strftime('%Y-%m-%d'),
                'media_type': media_type,
                'accessibility_caption': accessibility_caption
            })
    sorted_posts = sorted(recent_posts_with_scores, key=lambda p: p['interaction_score'], reverse=True)
    top_posts = sorted_posts[:6]
    avg_er = sum(post['engagement_rate'] for post in top_posts) / len(top_posts) if top_posts else 0
    return total_last_three_months_posts, top_posts, round(avg_er, 2)

def extract_hashtags_and_mentions(posts: List[dict], limit: int = 10) -> Dict:
    if not posts:
        return {'hashtags': {}, 'mentions': {}, 'total_posts_analyzed': 0, 'date_range': 'No posts found'}
    ninety_days_ago = datetime.datetime.now() - datetime.timedelta(days=90)
    ninety_days_ago_unix = int(ninety_days_ago.timestamp())
    hashtag_counts = {}
    mention_counts = {}
    posts_analyzed = 0
    for post in posts:
        try:
            if not post or not isinstance(post, dict):
                continue
            node = post.get('node', {})
            if not node:
                continue
            taken_at = node.get('taken_at', 0)
            if taken_at < ninety_days_ago_unix:
                continue
            posts_analyzed += 1
            caption_obj = node.get('caption')
            if not caption_obj or not isinstance(caption_obj, dict):
                continue
            caption_text = caption_obj.get('text', '')
            if not caption_text or not isinstance(caption_text, str):
                continue
            hashtags = re.findall(r'#([A-Za-z0-9_]+)', caption_text)
            for hashtag in hashtags:
                hashtag_lower = hashtag.lower()
                hashtag_counts[hashtag_lower] = hashtag_counts.get(hashtag_lower, 0) + 1
            mentions = re.findall(r'@([A-Za-z0-9._]+)', caption_text)
            for mention in mentions:
                if len(mention) >= 3 and mention.lower() not in ['the', 'and', 'for', 'from', 'with', 'this', 'that', 'have', 'has', 'her', 'his', 'our', 'my', 'your', 'their', 'its', 'as', 'at', 'by', 'to', 'in', 'on', 'of', 'or', 'if']:
                    mention_lower = mention.lower()
                    mention_counts[mention_lower] = mention_counts.get(mention_lower, 0) + 1
        except (AttributeError, TypeError, KeyError):
            continue
    top_hashtags = dict(sorted(hashtag_counts.items(), key=lambda x: x[1], reverse=True)[:limit])
    top_mentions = dict(sorted(mention_counts.items(), key=lambda x: x[1], reverse=True)[:limit])
    today_str = datetime.datetime.now().strftime('%Y-%m-%d')
    ninety_days_ago_str = ninety_days_ago.strftime('%Y-%m-%d')
    date_range = f"{ninety_days_ago_str} to {today_str}"
    return {'hashtags': top_hashtags, 'mentions': top_mentions, 'total_posts_analyzed': posts_analyzed, 'date_range': date_range}

def extract_email(user_info: dict) -> dict:
    user_data = user_info.get('data', {}).get('user', {})
    biography = user_data.get('biography', '') or ''
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, biography)
    if emails:
        return {'email': emails[0]}
    else:
        return {'email': None}

def extract_first_and_last_name(user_info: dict) -> dict:
    user_data = user_info.get('data', {}).get('user', {})
    full_name = user_data.get('full_name', '') or ''
    names = full_name.split()
    first_name = names[0] if names else None
    last_name = " ".join(names[1:]) if len(names) > 1 else None
    return {'first_name': first_name, 'last_name': last_name}

def determine_creator_size(user_info: dict) -> dict:
    user_data = user_info.get('data', {}).get('user', {})
    follower_count = user_data.get('follower_count', 0)
    if follower_count:
        if follower_count < 5000:
            creator_size = "Nano-Influencer"
        elif follower_count < 50000:
            creator_size = "Micro-Influencer"
        elif follower_count < 500000:
            creator_size = "Mid-Tier Influencer"
        elif follower_count < 1000000:
            creator_size = "Macro-Influencer"
        else:
            creator_size = "Mega-Influencer"
    else:
        creator_size = "Unknown"
    return creator_size

def extract_phone_number(user_info: dict) -> dict:
    user_data = user_info.get('data', {}).get('user', {})
    biography = user_data.get('biography', '') or ''
    patterns = [
        r'\+?\d{1,4}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}',
        r'\+\d{10,15}',
        r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
        r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\s*x\d{1,5}',
        r'\d{3,}[-.\s]?\d{3,}[-.\s]?\d{4,}'
    ]
    for pattern in patterns:
        match = re.search(pattern, biography)
        if match:
            phone_number = re.sub(r'[\s.-]', '', match.group(0))
            return {'phone_number': phone_number.strip()}
    return {'phone_number': None}

def get_latest_post_info(post_info: dict) -> dict:
    try:
        all_posts = post_info.get('data', {}).get('xdt_api__v1__feed__user_timeline_graphql_connection', {}).get('edges', [])
        if not all_posts:
            return {'latest_post_date': None, 'latest_post_link': None, 'latest_post_code': None, 'days_since_latest': None, 'error': 'No posts found'}
        latest_post = None
        latest_timestamp = 0
        for post in all_posts:
            try:
                node = post.get('node', {})
                taken_at = node.get('taken_at', 0)
                if taken_at > latest_timestamp:
                    latest_timestamp = taken_at
                    latest_post = node
            except (AttributeError, TypeError, KeyError):
                continue
        if not latest_post or latest_timestamp == 0:
            return {'latest_post_date': None, 'latest_post_link': None, 'latest_post_code': None, 'days_since_latest': None, 'error': 'No valid timestamps'}
        latest_date = datetime.datetime.fromtimestamp(latest_timestamp)
        latest_date_str = latest_date.strftime('%Y-%m-%d %H:%M:%S')
        current_date = datetime.datetime.now()
        days_since = (current_date - latest_date).days
        post_code = latest_post.get('code', '')
        instagram_link = f"https://www.instagram.com/p/{post_code}" if post_code else None
        return {'latest_post_date': latest_date_str, 'latest_post_link': instagram_link, 'latest_post_code': post_code, 'days_since_latest': days_since, 'error': None}
    except Exception as e:
        return {'latest_post_date': None, 'latest_post_link': None, 'latest_post_code': None, 'days_since_latest': None, 'error': f'Error: {str(e)}'}

def analyze_creator_data(creator_dir: str) -> dict:
    try:
        user_info_path = os.path.join(creator_dir, 'userInfo.json')
        post_info_path = os.path.join(creator_dir, 'postInfo.json')
        if not os.path.exists(user_info_path) or not os.path.exists(post_info_path):
            print(f"{Fore.RED}Missing files in {creator_dir}{Style.RESET_ALL}")
            return None
        user_info = load_json_file(user_info_path)
        post_info = load_json_file(post_info_path)
        if not user_info or not post_info:
            print(f"{Fore.RED}Failed to load data for {creator_dir}{Style.RESET_ALL}")
            return None
        all_posts = post_info.get('data', {}).get('xdt_api__v1__feed__user_timeline_graphql_connection', {}).get('edges', [])
        if not all_posts:
            print(f"{Fore.YELLOW}Skipping {creator_dir}: No posts found{Style.RESET_ALL}")
            return None

        location_analysis = extract_location_from_posts(all_posts)
        address_components = {'city': None, 'state': None, 'country': None}
        if location_analysis['primary_location']:
            primary_loc = next((loc for loc in location_analysis['all_locations'] if loc['name'] == location_analysis['primary_location']), None)
            if primary_loc:
                address_components = parse_location_to_address_components(location_analysis['primary_location'], primary_loc.get('address'), primary_loc.get('city'))

        social_links = extract_social_links(user_info)
        gender = identify_gender(user_info)
        email_info = extract_email(user_info)
        first_and_lastname = extract_first_and_last_name(user_info)
        creator_size = determine_creator_size(user_info)
        phone_number_info = extract_phone_number(user_info)

        total_posts, top_posts, avg_er = calculate_top_post_er(post_info, user_info)
        collaboration_data = identify_collaborations(all_posts)
        niche_data = identify_niche(user_info)
        creator_pricing_info = extract_creator_pricing(user_info, all_posts)
        hashtag_mention_data = extract_hashtags_and_mentions(all_posts, limit=10)
        basic_info = extract_basic_info(user_info)
        other_urls = extract_other_urls(user_info)

        scraped_timestamp = os.path.getctime(creator_dir)
        scraped_date = datetime.datetime.fromtimestamp(scraped_timestamp).strftime('%Y-%m-%d')

        return {
            'pk': basic_info.get('pk'),
            'fbid_v2': user_info.get('data', {}).get('user', {}).get('fbid_v2'),
            'account_type': user_info.get('data', {}).get('user', {}).get('account_type'),
            'media_count': user_info.get('data', {}).get('user', {}).get('media_count'),
            'total_clips_count': user_info.get('data', {}).get('user', {}).get('total_clips_count'),
            'pronouns': user_info.get('data', {}).get('user', {}).get('pronouns'),
            'other_urls': other_urls,
            'username': basic_info.get('username'),
            'full_name': basic_info.get('full_name'),
            'first_name': first_and_lastname.get('first_name'),
            'last_name': first_and_lastname.get('last_name'),
            'biography': basic_info.get('biography'),
            'phone_number': phone_number_info.get('phone_number'),
            'follower_count': basic_info.get('follower_count'),
            'creator_size': creator_size,
            'gender': gender,
            'email': email_info.get('email'),
            'business_category': basic_info.get('category'),
            'profile_picture': basic_info.get('profile_picture'),
            'social_links': social_links,
            'primary_location_name': location_analysis['primary_location'],
            'latitude': location_analysis['primary_lat'],
            'longitude': location_analysis['primary_lng'],
            'address_city': address_components['city'],
            'address_state': address_components['state'],
            'address_country': address_components['country'],
            'all_locations': location_analysis['all_locations'],
            'posts_with_location': location_analysis['posts_with_location'],
            'total_posts_scraped': location_analysis['total_posts'],
            'total_posts_last_3_months': total_posts,
            'top_6_posts': top_posts,
            'average_engagement_rate': avg_er,
            'collaboration_status': collaboration_data['status'],
            'total_collaborations': collaboration_data['total_collaborations'],
            'recent_collaborations': collaboration_data['recent_collaborations'],
            'ugc_examples': collaboration_data['ugc_examples'],
            'top_collaboration': collaboration_data['all_collaborations'],
            'niche_data': niche_data,
            'creator_type': creator_pricing_info.get('creator_type'),
            'tier': creator_pricing_info.get('tier'),
            'creator_pricing_metrics': creator_pricing_info.get('creator_pricing_metrics'),
            'hashtags_last_90_days': hashtag_mention_data['hashtags'],
            'mentions_last_90_days': hashtag_mention_data['mentions'],
            'posts_analyzed_for_hashtags': hashtag_mention_data['total_posts_analyzed'],
            'hashtag_analysis_date_range': hashtag_mention_data['date_range'],
            'latest_post_date': get_latest_post_info(post_info).get('latest_post_date'),
            'latest_post_link': get_latest_post_info(post_info).get('latest_post_link'),
            'analyzed_date': datetime.datetime.now().strftime('%Y-%m-%d'),
            'scraped_date': scraped_date
        }
    except Exception as e:
        print(f"{Fore.RED}Error analyzing {creator_dir}: {str(e)}{Style.RESET_ALL}")
        return None

def load_usernames_from_csv(csv_path: str) -> List[str]:
    usernames = []
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if 'username' not in reader.fieldnames:
                print(f"{Fore.RED}CSV must contain 'username' column{Style.RESET_ALL}")
                return []
            for row in reader:
                username = row.get('username')
                if username:
                    usernames.append(username.strip())
        print(f"{Fore.GREEN}Loaded {len(usernames)} usernames{Style.RESET_ALL}")
    except FileNotFoundError:
        print(f"{Fore.RED}CSV file not found{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error reading CSV: {str(e)}{Style.RESET_ALL}")
    return usernames

def main():
    print(f"{Fore.CYAN}Instagram Analyzer (full) - writing data/analyzed.json{Style.RESET_ALL}")
    base_path = os.path.join(os.getcwd(), 'data', 'output')
    if not os.path.exists(base_path):
        print(f"{Fore.RED}Output directory not found: {base_path}{Style.RESET_ALL}")
        return

    creators = [d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))]
    print(f"Found {len(creators)} creators")
    results = []
    succeeded = 0
    failed = 0
    for i, c in enumerate(creators, 1):
        path = os.path.join(base_path, c)
        print(f"[{i}/{len(creators)}] Analyzing {c}")
        r = analyze_creator_data(path)
        if r:
            results.append(r)
            succeeded += 1
        else:
            failed += 1

    combined = {
        'analysis_date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_creators_analyzed': succeeded,
        'creators_with_location': sum(1 for r in results if r.get('primary_location_name')),
        'location_coverage_percentage': round((sum(1 for r in results if r.get('primary_location_name')) / succeeded * 100) if succeeded else 0, 2),
        'creators': results
    }

    os.makedirs(os.path.join(os.getcwd(), 'data'), exist_ok=True)
    out_path = os.path.join(os.getcwd(), 'data', 'analyzed.json')
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(combined, f, indent=2, ensure_ascii=False)
        print(f"{Fore.GREEN}✓ Results saved: {out_path}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Failed to write analyzed.json: {e}{Style.RESET_ALL}")

if __name__ == '__main__':
    main()
