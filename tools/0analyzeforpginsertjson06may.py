import os, sys, json, re, datetime, csv, math, hashlib
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Optional, Tuple, Any
from colorama import init, Fore, Style
init(autoreset=True)

# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────
def load_json(path: str) -> dict:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"{Fore.RED}Error loading {path}: {e}{Style.RESET_ALL}")
        return {}

def ts_to_dt(ts) -> Optional[datetime.datetime]:
    try:
        return datetime.datetime.fromtimestamp(int(ts), tz=datetime.timezone.utc)
    except Exception:
        return None

def fmt_date(dt) -> str:
    if not dt:
        return ''
    if isinstance(dt, datetime.datetime):
        return dt.strftime('%Y-%m-%d')
    return str(dt)[:10]

def fmt_ts(dt) -> Optional[str]:
    if not dt:
        return None
    if isinstance(dt, datetime.datetime):
        return dt.isoformat()
    return str(dt)

def safe_div(a, b, default=0):
    return a / b if b else default

def safe_int(v, default=0):
    try:
        return int(v) if v is not None else default
    except Exception:
        return default

def safe_float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except Exception:
        return default

# ─────────────────────────────────────────────────────────────
#  POST EXTRACTION — handles all known API formats
# ─────────────────────────────────────────────────────────────
TIMELINE_KEYS = [
    'xdt_api__v1__feed__user_timeline_graphql_connection',
    'xdt_api__v1__feed__user_timeline',
    'user_timeline_graphql_connection',
    'user_timeline',
]

def get_posts(post_info: dict) -> List[dict]:
    data = post_info.get('data', {})
    for k in TIMELINE_KEYS:
        bucket = data.get(k)
        if bucket:
            if isinstance(bucket, dict):
                edges = bucket.get('edges', [])
                return [e.get('node', e) for e in edges]
            if isinstance(bucket, list):
                return bucket
    # flat list fallback
    if isinstance(data, list):
        return data
    return []

def best_image_url(image_versions2: dict) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """Return (url, width, height) for the best quality image."""
    candidates = (image_versions2 or {}).get('candidates', []) or []
    if not candidates:
        return None, None, None
    # Sort by area descending — pick largest
    best = max(candidates, key=lambda c: (c.get('width',0) or 0) * (c.get('height',0) or 0), default=None)
    if not best:
        return None, None, None
    return best.get('url'), best.get('width'), best.get('height')

def get_location_from_node(n: dict) -> dict:
    loc = n.get('location') or {}
    if not isinstance(loc, dict):
        return {}
    return {
        'pk':      str(loc.get('pk') or loc.get('id') or ''),
        'name':    loc.get('name'),
        'lat':     loc.get('lat') or loc.get('latitude'),
        'lng':     loc.get('lng') or loc.get('longitude'),
        'address': loc.get('address'),
        'city':    loc.get('city'),
    }

# ─────────────────────────────────────────────────────────────
#  MEDIA TYPE CONSTANTS
# ─────────────────────────────────────────────────────────────
MEDIA_TYPE_MAP = {1: 'Photo', 2: 'Video/Reel', 8: 'Carousel'}
PRODUCT_TYPE_MAP = {
    'clips': 'Reel',
    'carousel_container': 'Carousel',
    'feed': 'Photo',
    'carousel_item': 'Carousel Item',
    'igtv': 'IGTV',
}

def classify_post(n: dict) -> str:
    pt = n.get('product_type', '')
    mt = n.get('media_type')
    return PRODUCT_TYPE_MAP.get(pt) or MEDIA_TYPE_MAP.get(mt, 'Unknown')

# ─────────────────────────────────────────────────────────────
#  1. BASIC PROFILE  (every userInfo field)
# ─────────────────────────────────────────────────────────────
def basic_profile(ui: dict) -> dict:
    u = ui.get('data', {}).get('user', {}) or {}
    fs = u.get('friendship_status', {}) or {}
    ring = u.get('ring_creator_metadata', {}) or {}

    followers   = safe_int(u.get('follower_count'))
    following   = safe_int(u.get('following_count'))
    ff_ratio    = round(safe_div(followers, following), 4) if following else 0

    full_name   = u.get('full_name', '') or ''
    names = [p for p in full_name.split() if p]

    creator_size = (
        'Mega (1M+)'          if followers >= 1_000_000 else
        'Macro (500K–1M)'     if followers >= 500_000   else
        'Mid-Tier (50K–500K)' if followers >= 50_000    else
        'Micro (10K–50K)'     if followers >= 10_000    else
        'Nano (1K–10K)'       if followers >= 1_000     else
        'Beginner (<1K)'
    )

    return {
        'username':                  u.get('username', ''),
        'full_name':                 full_name,
        'first_name':                names[0] if names else None,
        'last_name':                 ' '.join(names[1:]) if len(names) > 1 else None,
        'biography':                 u.get('biography', ''),
        'pk':                        str(u.get('pk') or u.get('id') or ''),
        'fbid_v2':                   str(u.get('fbid_v2') or ''),
        'account_type':              u.get('account_type'),
        'is_verified':               bool(u.get('is_verified')),
        'is_business':               bool(u.get('is_business')),
        'is_private':                bool(u.get('is_private')),
        'is_professional_account':   u.get('is_professional_account'),
        'is_unpublished':            bool(u.get('is_unpublished')),
        'is_memorialized':           bool(u.get('is_memorialized')),
        'is_coppa_enforced':         bool(u.get('is_coppa_enforced')),
        'is_regulated_c18':          bool(u.get('is_regulated_c18')),
        'is_ring_creator':           bool(u.get('is_ring_creator')),
        'is_embeds_disabled':        bool(u.get('is_embeds_disabled')),
        'is_cannes':                 bool(u.get('is_cannes')),
        'show_ring_award':           bool(u.get('show_ring_award')),
        'show_text_post_app_badge':  bool(u.get('show_text_post_app_badge')),
        'remove_message_entrypoint': bool(u.get('remove_message_entrypoint')),
        'hide_creator_marketplace_badge': bool(u.get('hide_creator_marketplace_badge')),
        'has_chaining':              bool(u.get('has_chaining')),
        'follower_count':            followers,
        'following_count':           following,
        'media_count':               safe_int(u.get('media_count')),
        'total_clips_count':         safe_int(u.get('total_clips_count')),
        'ff_ratio':                  ff_ratio,
        'creator_size':              creator_size,
        'profile_pic_url':           (u.get('hd_profile_pic_url_info') or {}).get('url') or u.get('profile_pic_url', ''),
        'profile_pic_local':         f"https://assets.veelapp.com/{u.get('username','')}.jpg",
        'has_profile_pic':           u.get('has_profile_pic'),
        'external_url':              u.get('external_url', ''),
        'external_lynx_url':         u.get('external_lynx_url'),
        'category':                  u.get('category', ''),
        'business_category':         u.get('business_category'),  # from postInfo sometimes
        'should_show_category':      bool(u.get('should_show_category')),
        'address_street':            u.get('address_street', ''),
        'city_name':                 u.get('city_name', ''),
        'zip':                       u.get('zip', ''),
        'ai_agent_type':             u.get('ai_agent_type'),
        'transparency_label':        u.get('transparency_label'),
        'transparency_product':      u.get('transparency_product'),
        'latest_reel_media':         safe_int(u.get('latest_reel_media')),
        'latest_besties_reel_media': safe_int(u.get('latest_besties_reel_media')),
        'has_story_archive':         u.get('has_story_archive'),
        'reel_media_seen_timestamp': u.get('reel_media_seen_timestamp'),
        'pronouns':                  u.get('pronouns', []),
        # friendship status (viewer vs creator)
        'friendship': {
            'following':         bool(fs.get('following')),
            'blocking':          bool(fs.get('blocking')),
            'is_feed_favorite':  bool(fs.get('is_feed_favorite')),
            'outgoing_request':  bool(fs.get('outgoing_request')),
            'followed_by':       bool(fs.get('followed_by')),
            'incoming_request':  bool(fs.get('incoming_request')),
            'is_restricted':     bool(fs.get('is_restricted')),
            'is_bestie':         bool(fs.get('is_bestie')),
            'muting':            bool(fs.get('muting')),
            'is_muting_reel':    bool(fs.get('is_muting_reel')),
        },
    }

# ─────────────────────────────────────────────────────────────
#  2. CONTACT & LINKS  (bio + bio_links array)
# ─────────────────────────────────────────────────────────────
def extract_contacts(ui: dict) -> dict:
    u    = ui.get('data', {}).get('user', {}) or {}
    bio  = u.get('biography', '') or ''
    links = u.get('bio_links', []) or []

    email_m  = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', bio)
    phone_m  = re.search(r'(\+?\d[\d\s\-().]{7,}\d)', bio)

    social = {
        'tiktok': None, 'youtube': None, 'linktree': None, 'twitter_x': None,
        'facebook': None, 'spotify': None, 'other': [],
    }
    patterns = {
        'tiktok':    ['tiktok.com'],
        'youtube':   ['youtube.com', 'youtu.be'],
        'linktree':  ['linktr.ee'],
        'twitter_x': ['twitter.com', 'x.com'],
        'facebook':  ['facebook.com', 'fb.com'],
        'spotify':   ['spotify.com', 'open.spotify'],
    }

    parsed_links = []
    for lo in links:
        url = (lo.get('url', '') if isinstance(lo, dict) else str(lo)) or ''
        if not url:
            continue
        link_type = 'other'
        for platform, pats in patterns.items():
            if any(p in url.lower() for p in pats):
                social[platform] = url
                link_type = platform
                break
        else:
            social['other'].append(url)
        parsed_links.append({
            'url':          url,
            'type':         link_type,
            'display_text': lo.get('title') if isinstance(lo, dict) else None,
            'is_pinned':    bool(lo.get('is_pinned')) if isinstance(lo, dict) else False,
        })

    return {
        'email':         email_m.group(0) if email_m else None,
        'phone':         re.sub(r'[\s\-().]', '', phone_m.group(0)).strip() if phone_m else None,
        'social_links':  social,
        'parsed_links':  parsed_links,
        'raw_links':     [lo.get('url', '') for lo in links if isinstance(lo, dict)],
    }

# ─────────────────────────────────────────────────────────────
#  3. GENDER DETECTION
# ─────────────────────────────────────────────────────────────
def detect_gender(ui: dict) -> str:
    u   = ui.get('data', {}).get('user', {}) or {}
    pro = u.get('pronouns', []) or []
    for p in pro:
        pt = (p.get('pronoun', '') if isinstance(p, dict) else str(p)).lower()
        if any(x in pt for x in ['she', 'her']):   return 'Female'
        if any(x in pt for x in ['he', 'him']):    return 'Male'
        if any(x in pt for x in ['they', 'them']): return 'Non-binary'

    text = ' '.join([
        u.get('biography', '') or '',
        u.get('full_name', '') or '',
        u.get('username', '') or ''
    ]).lower()
    female = sum(text.count(w) for w in [
        'she', 'her', 'woman', 'girl', 'mom', 'mother', 'wife',
        'daughter', 'sister', 'queen', 'actress', 'mama', 'lady', 'bae', 'babe'
    ])
    male = sum(text.count(w) for w in [
        'he', 'him', 'man', 'boy', 'dad', 'father', 'husband',
        'son', 'brother', 'king', 'actor', 'papa', 'guy', 'bro'
    ])
    if female > male:   return 'Female'
    if male > female:   return 'Male'
    return 'Unknown'

# ─────────────────────────────────────────────────────────────
#  4. NICHE DETECTION
# ─────────────────────────────────────────────────────────────
NICHES = {
    'Fashion & Style':   ['fashion','style','outfit','ootd','clothing','model','dress','stylist','wardrobe','chic','accessory','boutique'],
    'Beauty':            ['makeup','beauty','skincare','cosmetics','haircare','nails','glam','mua','makeover','mehendi','henna','bridal'],
    'Lifestyle':         ['lifestyle','daily','routine','inspiration','motivation','blogger','living','vibes','mindful','life','vlog'],
    'Fitness':           ['fitness','workout','gym','exercise','training','fit','yoga','pilates','crossfit','bodybuilding','curls'],
    'Health & Wellness': ['health','wellness','nutrition','diet','meditation','nutritionist','holistic','wellbeing','vet','veterinary'],
    'Food':              ['food','cooking','recipe','chef','foodie','baking','culinary','restaurant','tasty','kitchen','thakali','cuisine'],
    'Travel':            ['travel','wanderlust','adventure','explore','tourism','vacation','trip','nomad','backpacker','traveller','explorer'],
    'Technology':        ['technology','tech','gadget','software','app','coding','developer','startup','digital'],
    'Gaming':            ['gaming','gamer','game','esports','streamer','twitch','console','playstation','xbox','pubg','freefire'],
    'Entertainment':     ['entertainment','movie','film','tv','cinema','streaming','celebrity','show','series','actor','filmmaker'],
    'Comedy':            ['comedy','funny','humor','laugh','joke','prank','comedian','meme','viral','tiktok'],
    'Education':         ['education','learning','school','knowledge','teach','study','lesson','tutor','academic','student'],
    'Business':          ['business','entrepreneur','marketing','startup','success','ceo','founder','leadership'],
    'Finance':           ['finance','investing','stocks','crypto','money','financial','wealth','trader'],
    'Art & Design':      ['art','artist','drawing','painting','creative','design','illustration','designer','photographer'],
    'Music':             ['music','musician','song','singer','band','concert','producer','dj','songwriter','rapper','audio','sound'],
    'Dance':             ['dance','dancer','choreography','ballet','hiphop','contemporary','choreographer'],
    'Sports':            ['sports','athlete','basketball','football','soccer','tennis','coach','player','championship','badminton','bike','motorcycle'],
    'Pets':              ['pets','dog','cat','puppy','kitten','wildlife','petcare','rescue','animallover'],
    'Family':            ['family','parenting','mom','dad','children','kids','baby','motherhood','fatherhood','husband','wife'],
    'Photography':       ['photography','photographer','photo','shots','camera','portrait','streetphotography','cinematic','cinematography'],
    'Nature':            ['nature','hike','hiking','outdoors','mountains','forest','landscape','wildlife','trek','adventure'],
    'Spirituality':      ['temple','spiritual','divine','god','prayer','puja','theyyam','ritual','bhakti'],
}

def detect_niche(ui: dict, posts: List[dict]) -> dict:
    u    = ui.get('data', {}).get('user', {}) or {}
    bio  = (u.get('biography', '') or '').lower()
    name = (u.get('full_name', '') or '').lower()
    user = (u.get('username', '') or '').lower().replace('_', ' ').replace('.', ' ')
    cat  = (u.get('category', '') or '').lower()

    all_caps = []
    hashtags_all = []
    for n in posts:
        if (n.get('product_type') or '') == 'carousel_item':
            continue
        cap_obj = n.get('caption') or {}
        cap = (cap_obj.get('text', '') if isinstance(cap_obj, dict) else '') or ''
        all_caps.append(cap.lower())
        hashtags_all += re.findall(r'#(\w+)', cap.lower())

    combined_text = ' '.join([bio, name, user, cat] + all_caps)

    scores = {}
    matched = {}
    for niche, keywords in NICHES.items():
        hits = [k for k in keywords if k in combined_text]
        scores[niche] = sum(combined_text.count(k) for k in keywords)
        matched[niche] = hits

    total = sum(scores.values()) or 1
    dist  = {k: round(v / total * 100, 1) for k, v in scores.items() if v > 0}
    dist  = dict(sorted(dist.items(), key=lambda x: -x[1])[:8])

    top = max(scores, key=scores.get) if any(scores.values()) else None
    top_hashtags = Counter(hashtags_all).most_common(30)

    return {
        'primary_niche':           top if scores.get(top, 0) > 0 else 'General',
        'niche_distribution':      dist,
        'matched_keywords':        matched.get(top, []) if top else [],
        'top_hashtags_overall':    dict(top_hashtags),
        'hashtag_count_total':     len(hashtags_all),
        'unique_hashtags':         len(set(hashtags_all)),
    }

# ─────────────────────────────────────────────────────────────
#  5. CONTENT DNA
# ─────────────────────────────────────────────────────────────
def analyze_content_dna(posts: List[dict]) -> dict:
    if not posts:
        return {}

    now       = datetime.datetime.now(tz=datetime.timezone.utc)
    dts       = []
    type_counts = Counter()
    lengths   = []
    cap_words = []
    has_caption = has_location = has_usertags = 0
    carousel_sizes = []
    total_posts = 0

    for n in posts:
        if (n.get('product_type') or '') == 'carousel_item':
            continue
        total_posts += 1

        ts = n.get('taken_at')
        dt = ts_to_dt(ts)
        if dt:
            dts.append(dt)

        label = classify_post(n)
        type_counts[label] += 1

        cap_obj = n.get('caption') or {}
        cap = (cap_obj.get('text', '') if isinstance(cap_obj, dict) else '') or ''
        if cap.strip():
            has_caption += 1
            wds = cap.split()
            cap_words.append(len(wds))
            lengths.append(len(cap))

        loc = n.get('location')
        if loc and isinstance(loc, dict) and loc.get('name'):
            has_location += 1

        tags = (n.get('usertags') or {}).get('in', []) or []
        if tags:
            has_usertags += 1

        cm = n.get('carousel_media_count')
        if cm and safe_int(cm) > 1:
            carousel_sizes.append(safe_int(cm))

    dts_sorted = sorted(dts)
    gaps_days  = []
    if len(dts_sorted) > 1:
        for i in range(1, len(dts_sorted)):
            gap = (dts_sorted[i] - dts_sorted[i - 1]).days
            gaps_days.append(abs(gap))

    avg_gap          = round(safe_div(sum(gaps_days), len(gaps_days)), 1) if gaps_days else 0
    posts_per_week   = round(safe_div(7, avg_gap), 2) if avg_gap > 0 else 0
    posts_per_month  = round(posts_per_week * 4.3, 1)

    if len(gaps_days) > 1:
        mean_gap = safe_div(sum(gaps_days), len(gaps_days))
        variance = safe_div(sum((g - mean_gap) ** 2 for g in gaps_days), len(gaps_days))
        std_dev  = math.sqrt(variance)
        consistency = max(0, round(100 - min(std_dev * 3, 100)))
    else:
        consistency = 50

    avg_cap_len   = round(safe_div(sum(lengths), max(len(lengths), 1)))
    avg_cap_words = round(safe_div(sum(cap_words), max(len(cap_words), 1)))
    caption_style = (
        'Minimal (emoji/hashtag only)' if avg_cap_words < 5  else
        'Short & Punchy'               if avg_cap_words < 20 else
        'Medium Storytelling'          if avg_cap_words < 60 else
        'Long-form / Detailed'
    )

    first_post    = fmt_date(dts_sorted[0])  if dts_sorted else ''
    last_post     = fmt_date(dts_sorted[-1]) if dts_sorted else ''
    days_span     = (dts_sorted[-1] - dts_sorted[0]).days if len(dts_sorted) > 1 else 0
    days_inactive = (now - dts_sorted[-1]).days if dts_sorted else None
    activity_status = (
        'Highly Active' if days_inactive is not None and days_inactive <= 7  else
        'Active'        if days_inactive is not None and days_inactive <= 21 else
        'Moderate'      if days_inactive is not None and days_inactive <= 45 else
        'Inactive'      if days_inactive is not None and days_inactive <= 90 else
        'Dormant'
    )

    return {
        'total_posts_analyzed':        total_posts,
        'content_type_mix':            dict(type_counts),
        'dominant_format':             type_counts.most_common(1)[0][0] if type_counts else 'Unknown',
        'avg_carousel_slides':         round(safe_div(sum(carousel_sizes), max(len(carousel_sizes), 1)), 1),
        'posts_with_caption_pct':      round(safe_div(has_caption, max(total_posts, 1)) * 100, 2),
        'posts_with_location_pct':     round(safe_div(has_location, max(total_posts, 1)) * 100, 2),
        'posts_with_usertags_pct':     round(safe_div(has_usertags, max(total_posts, 1)) * 100, 2),
        'avg_caption_length_chars':    avg_cap_len,
        'avg_caption_words':           avg_cap_words,
        'caption_style':               caption_style,
        'first_post_date':             first_post,
        'last_post_date':              last_post,
        'days_span_scraped':           days_span,
        'days_since_last_post':        days_inactive,
        'activity_status':             activity_status,
        'avg_days_between_posts':      avg_gap,
        'estimated_posts_per_week':    posts_per_week,
        'estimated_posts_per_month':   posts_per_month,
        'posting_consistency_score':   consistency,
    }

# ─────────────────────────────────────────────────────────────
#  6. ENGAGEMENT ANALYTICS
# ─────────────────────────────────────────────────────────────
def analyze_engagement(posts: List[dict], followers: int) -> dict:
    if not posts or followers == 0:
        return {}

    now         = datetime.datetime.now(tz=datetime.timezone.utc)
    ninety_ago  = now - datetime.timedelta(days=90)

    all_metrics    = []
    recent_metrics = []
    viral_posts    = []

    for n in posts:
        if (n.get('product_type') or '') == 'carousel_item':
            continue

        likes    = safe_int(n.get('like_count'))
        comments = safe_int(n.get('comment_count'))
        views    = n.get('view_count')
        ts       = n.get('taken_at')
        dt       = ts_to_dt(ts)
        code     = n.get('code', '') or n.get('shortcode', '') or ''
        fb_likes = n.get('fb_like_count')
        reposts  = n.get('media_repost_count')

        weighted   = likes + 5 * comments
        er_w       = safe_div(weighted, followers) * 100
        er_simple  = safe_div(likes + comments, followers) * 100

        meta = {
            'code':            code,
            'url':             f'https://www.instagram.com/p/{code}' if code else '',
            'date':            fmt_date(dt),
            'taken_at_ts':     fmt_ts(dt),
            'likes':           likes,
            'comments':        comments,
            'views':           views,
            'fb_likes':        fb_likes,
            'reposts':         reposts,
            'er_weighted':     round(er_w, 4),
            'er_simple':       round(er_simple, 4),
            'interaction_score': weighted,
            'product_type':    n.get('product_type', ''),
            'media_type':      n.get('media_type'),
            'caption_snippet': ((n.get('caption') or {}).get('text', '') or '')[:120],
            'is_paid_partnership': bool(n.get('is_paid_partnership')),
            'has_audio':       n.get('has_audio'),
            'location_name':   (n.get('location') or {}).get('name') if isinstance(n.get('location'), dict) else None,
        }
        all_metrics.append(meta)
        if dt and dt >= ninety_ago:
            recent_metrics.append(meta)

    if not all_metrics:
        return {}

    avg_likes    = round(safe_div(sum(m['likes'] for m in all_metrics), len(all_metrics)))
    avg_comments = round(safe_div(sum(m['comments'] for m in all_metrics), len(all_metrics)), 2)
    avg_er       = round(safe_div(sum(m['er_weighted'] for m in all_metrics), len(all_metrics)), 4)

    viral_threshold = avg_er * 2
    viral_posts = [m for m in all_metrics if m['er_weighted'] >= viral_threshold]

    top6     = sorted(all_metrics, key=lambda x: x['er_weighted'], reverse=True)[:6]
    avg_top6 = round(safe_div(sum(m['er_weighted'] for m in top6), max(len(top6), 1)), 4)
    avg_er_recent = round(safe_div(sum(m['er_weighted'] for m in recent_metrics), max(len(recent_metrics), 1)), 4)

    er_grade = (
        'S (Elite)'     if avg_er >= 6   else
        'A (Excellent)' if avg_er >= 3   else
        'B (Good)'      if avg_er >= 1.5 else
        'C (Average)'   if avg_er >= 0.5 else
        'D (Below Avg)'
    )
    lc_ratio = round(safe_div(avg_likes, max(avg_comments, 1)), 2)
    audience_type = (
        'Niche & Highly Engaged' if lc_ratio < 20 else
        'Balanced'               if lc_ratio < 60 else
        'Broad / Passive'
    )

    return {
        'avg_likes':                avg_likes,
        'avg_comments':             avg_comments,
        'avg_er_weighted':          avg_er,
        'avg_er_simple':            round(safe_div(sum(m['er_simple'] for m in all_metrics), len(all_metrics)), 4),
        'avg_er_top6':              avg_top6,
        'avg_er_last_90_days':      avg_er_recent,
        'er_grade':                 er_grade,
        'like_comment_ratio':       lc_ratio,
        'audience_engagement_type': audience_type,
        'total_likes_all_posts':    sum(m['likes'] for m in all_metrics),
        'total_comments_all_posts': sum(m['comments'] for m in all_metrics),
        'viral_posts_count':        len(viral_posts),
        'viral_posts':              viral_posts[:5],
        'top6_posts':               top6,
        'recent_posts_90d':         len(recent_metrics),
        'all_post_metrics':         all_metrics,
    }

# ─────────────────────────────────────────────────────────────
#  7. FULL POST DATA (every field from postInfo.json node)
# ─────────────────────────────────────────────────────────────
AD_TAGS = ['#ad', '#collab', '#sponsored', '#partnership', '#gifted',
           '#brandpartner', '#collaboration', '#paid', '#prreview', '#gifted']

def extract_full_posts(posts: List[dict], username: str) -> List[dict]:
    """Extract every field from every post node."""
    result = []
    for n in posts:
        if (n.get('product_type') or '') == 'carousel_item':
            continue

        code = n.get('code', '') or ''
        pk   = str(n.get('pk') or n.get('id') or '')

        # Caption
        cap_obj  = n.get('caption') or {}
        cap_text = (cap_obj.get('text', '') if isinstance(cap_obj, dict) else '') or ''
        hashtags = re.findall(r'#(\w+)', cap_text)
        mentions = re.findall(r'@([A-Za-z0-9._]+)', cap_text)
        cap_lower = cap_text.lower()
        ad_tags_found = [t for t in AD_TAGS if t in cap_lower]

        # Media
        img_url, img_w, img_h = best_image_url(n.get('image_versions2') or {})
        all_images = (n.get('image_versions2') or {}).get('candidates', []) or []

        # Video
        video_versions = n.get('video_versions') or []
        best_video     = video_versions[0] if video_versions else {}

        # Clips metadata
        clips = n.get('clips_metadata') or {}
        music = clips.get('music_info') or {}
        orig_sound = clips.get('original_sound_info') or {}
        ig_artist  = orig_sound.get('ig_artist') or {}

        # Location
        loc_info = get_location_from_node(n)

        # Owner / poster
        poster   = n.get('user') or {}
        owner    = n.get('owner') or {}

        # Coauthors
        coauthors = [
            {
                'pk':      str(c.get('pk') or c.get('id') or ''),
                'username': c.get('username', ''),
                'full_name': c.get('full_name', ''),
                'is_verified': bool(c.get('is_verified')),
                'profile_pic_url': c.get('profile_pic_url') or (c.get('hd_profile_pic_url_info') or {}).get('url'),
                'is_invited': False,
            }
            for c in (n.get('coauthor_producers') or [])
            if isinstance(c, dict)
        ]
        invited_coauthors = [
            {
                'pk':      str(c.get('pk') or c.get('id') or ''),
                'username': c.get('username', ''),
                'full_name': c.get('full_name', ''),
                'is_verified': bool(c.get('is_verified')),
                'profile_pic_url': c.get('profile_pic_url') or (c.get('hd_profile_pic_url_info') or {}).get('url'),
                'is_invited': True,
            }
            for c in (n.get('invited_coauthor_producers') or [])
            if isinstance(c, dict)
        ]

        # Usertags
        usertags = []
        for t in (n.get('usertags') or {}).get('in', []) or []:
            u = t.get('user', {}) or {}
            pos = t.get('position', []) or []
            usertags.append({
                'pk':       str(u.get('pk') or u.get('id') or ''),
                'username': u.get('username', ''),
                'full_name': u.get('full_name', ''),
                'is_verified': bool(u.get('is_verified')),
                'position_x': pos[0] if len(pos) > 0 else None,
                'position_y': pos[1] if len(pos) > 1 else None,
            })

        # Top likers
        top_likers = []
        for lk in (n.get('top_likers') or []):
            if isinstance(lk, dict):
                top_likers.append({
                    'pk': str(lk.get('pk') or lk.get('id') or ''),
                    'username': lk.get('username', ''),
                })
            elif isinstance(lk, str):
                top_likers.append({'pk': '', 'username': lk})

        # Carousel items
        carousel_items = []
        for idx, ci in enumerate(n.get('carousel_media') or []):
            ci_img, ci_iw, ci_ih = best_image_url(ci.get('image_versions2') or {})
            ci_vids = ci.get('video_versions') or []
            carousel_items.append({
                'position':         idx,
                'pk':               str(ci.get('pk') or ''),
                'id':               str(ci.get('id') or ''),
                'carousel_parent_id': ci.get('carousel_parent_id', ''),
                'media_type':       ci.get('media_type'),
                'original_width':   ci.get('original_width'),
                'original_height':  ci.get('original_height'),
                'has_audio':        ci.get('has_audio'),
                'is_dash_eligible': ci.get('is_dash_eligible'),
                'image_url':        ci_img,
                'video_url':        ci_vids[0].get('url') if ci_vids else None,
            })

        result.append({
            # --- Core identifiers ---
            'post_pk':                  pk,
            'post_id':                  str(n.get('id') or ''),
            'code':                     code,
            'post_url':                 f'https://www.instagram.com/p/{code}' if code else '',
            'typename':                 n.get('__typename', ''),

            # --- Media type ---
            'media_type':               n.get('media_type'),
            'product_type':             n.get('product_type', ''),
            'original_width':           n.get('original_width'),
            'original_height':          n.get('original_height'),
            'aspect_ratio':             round(safe_div(n.get('original_width', 0) or 0,
                                                        n.get('original_height', 1) or 1), 4),

            # --- Caption ---
            'caption_text':             cap_text,
            'caption_pk':               str(cap_obj.get('pk', '') if isinstance(cap_obj, dict) else ''),
            'caption_created_at':       fmt_ts(ts_to_dt(cap_obj.get('created_at'))) if isinstance(cap_obj, dict) else None,
            'caption_is_edited':        bool(n.get('caption_is_edited')),
            'caption_has_translation':  cap_obj.get('has_translation') if isinstance(cap_obj, dict) else None,
            'accessibility_caption':    n.get('accessibility_caption'),
            'title':                    n.get('title'),
            'headline':                 n.get('headline'),
            'taken_at':                 fmt_ts(ts_to_dt(n.get('taken_at'))),

            # --- Engagement ---
            'like_count':               safe_int(n.get('like_count')),
            'comment_count':            safe_int(n.get('comment_count')),
            'view_count':               n.get('view_count'),
            'fb_like_count':            n.get('fb_like_count'),
            'media_repost_count':       n.get('media_repost_count'),
            'like_and_view_counts_disabled': bool(n.get('like_and_view_counts_disabled')),
            'hidden_likes_string_variant': n.get('hidden_likes_string_variant'),
            'has_liked':                bool(n.get('has_liked')),
            'has_viewer_saved':         n.get('has_viewer_saved'),
            'photo_of_you':             bool(n.get('photo_of_you')),

            # --- Sponsorship ---
            'is_paid_partnership':      bool(n.get('is_paid_partnership')),
            'sponsor_tags':             n.get('sponsor_tags'),
            'affiliate_info':           n.get('affiliate_info'),
            'is_ad':                    bool(ad_tags_found),
            'ad_tags_found':            ad_tags_found,

            # --- Video / audio ---
            'has_audio':                n.get('has_audio'),
            'is_dash_eligible':         bool(n.get('is_dash_eligible')),
            'number_of_qualities':      n.get('number_of_qualities'),
            'video_url':                best_video.get('url') if best_video else None,
            'video_width':              best_video.get('width') if best_video else None,
            'video_height':             best_video.get('height') if best_video else None,
            'video_type':               best_video.get('type') if best_video else None,

            # --- Carousel ---
            'carousel_media_count':     n.get('carousel_media_count'),
            'carousel_parent_id':       n.get('carousel_parent_id'),
            'carousel_items':           carousel_items,

            # --- Location ---
            'location_pk':              loc_info.get('pk'),
            'location_name':            loc_info.get('name'),
            'location_lat':             loc_info.get('lat'),
            'location_lng':             loc_info.get('lng'),
            'location_address':         loc_info.get('address'),
            'location_city':            loc_info.get('city'),

            # --- Distribution ---
            'can_reshare':              n.get('can_reshare'),
            'can_viewer_reshare':       bool(n.get('can_viewer_reshare')),
            'ig_media_sharing_disabled': bool(n.get('ig_media_sharing_disabled')),
            'is_shared_from_basel':     n.get('is_shared_from_basel'),

            # --- Poster / owner ---
            'owner_id':                 str(owner.get('id') or poster.get('pk') or ''),
            'poster_username':          poster.get('username', ''),
            'poster_full_name':         poster.get('full_name', ''),
            'poster_is_verified':       bool(poster.get('is_verified')),
            'poster_profile_pic_url':   (poster.get('hd_profile_pic_url_info') or {}).get('url') or poster.get('profile_pic_url'),

            # --- Boost ---
            'boosted_status':           n.get('boosted_status'),
            'boost_unavailable_identifier': n.get('boost_unavailable_identifier'),
            'boost_unavailable_reason': n.get('boost_unavailable_reason'),

            # --- Clips metadata ---
            'clips_audio_type':         clips.get('audio_type'),
            'clips_is_shared_to_fb':    clips.get('is_shared_to_fb'),
            'clips_original_audio_title': orig_sound.get('original_audio_title'),
            'clips_audio_asset_id':     orig_sound.get('audio_asset_id'),
            'clips_ig_artist_username': ig_artist.get('username'),
            'clips_is_explicit':        orig_sound.get('is_explicit'),

            # --- Other ---
            'timeline_pinned_user_ids': n.get('timeline_pinned_user_ids') or [],
            'inventory_source':         n.get('inventory_source'),
            'audience':                 n.get('audience'),
            'profile_grid_thumbnail_style': n.get('profile_grid_thumbnail_fitting_style'),
            'is_seen':                  n.get('is_seen'),
            'organic_tracking_token':   (n.get('organic_tracking_token') or '')[:100],

            # --- Extracted ---
            'hashtags_in_caption':      hashtags,
            'mentions_in_caption':      mentions,
            'hashtag_count':            len(hashtags),
            'mention_count':            len(mentions),
            'caption_word_count':       len(cap_text.split()) if cap_text else 0,
            'caption_char_count':       len(cap_text) if cap_text else 0,

            # --- Image versions (all) ---
            'image_url_best':           img_url,
            'image_width_best':         img_w,
            'image_height_best':        img_h,
            'all_image_candidates':     all_images,
            'all_video_versions':       video_versions,

            # --- Relations ---
            'coauthors':                coauthors + invited_coauthors,
            'usertags':                 usertags,
            'top_likers':               top_likers,
        })

    return result

# ─────────────────────────────────────────────────────────────
#  8. BRAND & COLLABORATION INTELLIGENCE
# ─────────────────────────────────────────────────────────────
def analyze_brands(posts: List[dict], username: str) -> dict:
    now           = datetime.datetime.now(tz=datetime.timezone.utc)
    recent_cutoff = now - datetime.timedelta(days=180)
    brands  = {}
    paid_posts = []
    ad_posts   = []

    for n in posts:
        code = n.get('code', '') or ''
        ts   = n.get('taken_at')
        dt   = ts_to_dt(ts)
        is_recent = (dt >= recent_cutoff) if dt else False
        url  = f'https://www.instagram.com/p/{code}' if code else ''
        cap_obj  = n.get('caption') or {}
        cap_text = (cap_obj.get('text', '') if isinstance(cap_obj, dict) else '') or ''
        cap_lower = cap_text.lower()

        if n.get('is_paid_partnership'):
            paid_posts.append({'url': url, 'date': fmt_date(dt)})

        ad_tags_found = [t for t in AD_TAGS if t in cap_lower]
        if ad_tags_found:
            ad_posts.append({'url': url, 'date': fmt_date(dt), 'tags': ad_tags_found})

        mentions  = re.findall(r'@([A-Za-z0-9._]+)', cap_text)
        coauthors = [c.get('username', '') for c in (n.get('coauthor_producers') or []) if isinstance(c, dict)]
        tagged    = [t['user']['username'] for t in (n.get('usertags', {}) or {}).get('in', [])
                     if isinstance(t, dict) and t.get('user', {}).get('username')]

        all_signals = set(mentions + coauthors + tagged)
        all_signals.discard(username)

        for brand in all_signals:
            if not brand:
                continue
            if brand not in brands:
                brands[brand] = {'mention_count': 0, 'recent': False, 'posts': [], 'sources': []}
            brands[brand]['mention_count'] += 1
            if is_recent:
                brands[brand]['recent'] = True
            brands[brand]['posts'].append(url)
            if brand in coauthors:
                brands[brand]['sources'].append('coauthor')
            if brand in tagged:
                brands[brand]['sources'].append('usertag')
            if brand in mentions:
                brands[brand]['sources'].append('caption_mention')

    brands_sorted = sorted(brands.items(), key=lambda x: -x[1]['mention_count'])
    collaboration_status = (
        'Active (Paid)' if paid_posts else
        'Active (#ad)'  if ad_posts   else
        'Organic/Collab' if brands    else
        'No Collabs Found'
    )

    return {
        'collaboration_status':   collaboration_status,
        'paid_partnership_posts': len(paid_posts),
        'ad_tagged_posts':        len(ad_posts),
        'total_unique_brands':    len(brands),
        'top_brands':             [{'username': b, **d} for b, d in brands_sorted[:30]],
        'paid_post_examples':     paid_posts[:5],
        'ad_post_examples':       ad_posts[:5],
        'is_brand_active':        bool(paid_posts or ad_posts),
        'brand_frequency':        {b: d['mention_count'] for b, d in brands_sorted[:15]},
    }

# ─────────────────────────────────────────────────────────────
#  9. LOCATION INTELLIGENCE
# ─────────────────────────────────────────────────────────────
def analyze_locations(posts: List[dict]) -> dict:
    loc_list = []
    loc_freq = Counter()

    for n in posts:
        if (n.get('product_type') or '') == 'carousel_item':
            continue
        loc_info = get_location_from_node(n)
        name = loc_info.get('name')
        if not name:
            continue
        dt   = ts_to_dt(n.get('taken_at'))
        code = n.get('code', '')
        loc_freq[name] += 1
        loc_list.append({
            'location_pk':   loc_info.get('pk', ''),
            'name':          name,
            'lat':           loc_info.get('lat'),
            'lng':           loc_info.get('lng'),
            'address':       loc_info.get('address'),
            'city':          loc_info.get('city'),
            'post_code':     code,
            'post_url':      f'https://www.instagram.com/p/{code}' if code else '',
            'post_taken_at': fmt_date(dt),
        })

    primary = loc_freq.most_common(1)[0][0] if loc_freq else None
    primary_data = next((l for l in loc_list if l['name'] == primary), {})
    unique_coords = list({(l['lat'], l['lng']) for l in loc_list if l['lat'] and l['lng']})

    return {
        'posts_with_location':  len(loc_list),
        'unique_locations':     len(loc_freq),
        'primary_location':     primary,
        'primary_lat':          primary_data.get('lat'),
        'primary_lng':          primary_data.get('lng'),
        'location_frequency':   dict(loc_freq.most_common(10)),
        'all_locations':        loc_list,
        'is_traveler':          len(unique_coords) >= 3,
        'unique_coords_count':  len(unique_coords),
    }

# ─────────────────────────────────────────────────────────────
#  10. CAPTION INTELLIGENCE
# ─────────────────────────────────────────────────────────────
LANGUAGE_PATTERNS = {
    'Nepali/Devanagari': re.compile(r'[\u0900-\u097F]'),
    'Arabic':            re.compile(r'[\u0600-\u06FF]'),
    'Chinese':           re.compile(r'[\u4E00-\u9FFF]'),
    'Korean':            re.compile(r'[\uAC00-\uD7A3]'),
    'Japanese':          re.compile(r'[\u3040-\u30FF]'),
    'Thai':              re.compile(r'[\u0E00-\u0E7F]'),
    'Malayalam':         re.compile(r'[\u0D00-\u0D7F]'),
    'Tamil':             re.compile(r'[\u0B80-\u0BFF]'),
    'Bengali':           re.compile(r'[\u0980-\u09FF]'),
}
CTA_PATTERNS = [
    'link in bio', 'swipe', 'comment below', 'tag a friend', 'share this',
    'follow', 'dm me', 'dm for', 'save this', 'check out', 'shop now', 'buy now',
    'click link', 'watch', 'listen', 'subscribe', 'tap link', 'visit', 'book now',
]

def analyze_captions(posts: List[dict]) -> dict:
    caps = []
    languages   = Counter()
    cta_found   = Counter()
    emoji_posts = 0
    hashtag_counts = []
    mention_counts = []

    for n in posts:
        if (n.get('product_type') or '') == 'carousel_item':
            continue
        cap_obj = n.get('caption') or {}
        cap = (cap_obj.get('text', '') if isinstance(cap_obj, dict) else '') or ''
        if not cap.strip():
            continue
        caps.append(cap)

        detected = [lang for lang, pat in LANGUAGE_PATTERNS.items() if pat.search(cap)]
        if not detected:
            detected = ['English/Latin']
        for l in detected:
            languages[l] += 1

        cap_l = cap.lower()
        for cta in CTA_PATTERNS:
            if cta in cap_l:
                cta_found[cta] += 1

        if re.search(r'[\U0001F300-\U0001FAFF]', cap):
            emoji_posts += 1

        hashtag_counts.append(len(re.findall(r'#\w+', cap)))
        mention_counts.append(len(re.findall(r'@\w+', cap)))

    n_caps = max(len(caps), 1)
    avg_hashtags = round(safe_div(sum(hashtag_counts), max(len(hashtag_counts), 1)), 2)
    avg_mentions = round(safe_div(sum(mention_counts), max(len(mention_counts), 1)), 2)
    hashtag_strategy = (
        'Over-tagging (30+)' if avg_hashtags >= 30 else
        'Heavy (15–29)'      if avg_hashtags >= 15 else
        'Moderate (6–14)'    if avg_hashtags >= 6  else
        'Light (1–5)'        if avg_hashtags >= 1  else
        'No Hashtags'
    )

    return {
        'posts_with_captions':   len(caps),
        'languages_detected':    dict(languages.most_common()),
        'primary_language':      languages.most_common(1)[0][0] if languages else 'Unknown',
        'emoji_usage_pct':       round(safe_div(emoji_posts, n_caps) * 100, 2),
        'avg_hashtags_per_post': avg_hashtags,
        'avg_mentions_per_post': avg_mentions,
        'hashtag_strategy':      hashtag_strategy,
        'cta_usage':             dict(cta_found.most_common(15)),
        'uses_cta':              bool(cta_found),
    }

# ─────────────────────────────────────────────────────────────
#  11. HASHTAGS & MENTIONS (last 90 days)
# ─────────────────────────────────────────────────────────────
def extract_hashtags_mentions(posts: List[dict]) -> dict:
    now        = datetime.datetime.now(tz=datetime.timezone.utc)
    cutoff     = now - datetime.timedelta(days=90)
    hashtags   = Counter()
    mentions   = Counter()
    recent_count = 0

    for n in posts:
        if (n.get('product_type') or '') == 'carousel_item':
            continue
        dt = ts_to_dt(n.get('taken_at'))
        if not dt or dt < cutoff:
            continue
        recent_count += 1
        cap_obj = n.get('caption') or {}
        cap = (cap_obj.get('text', '') if isinstance(cap_obj, dict) else '') or ''
        for h in re.findall(r'#(\w+)', cap):
            hashtags[h.lower()] += 1
        for m in re.findall(r'@([A-Za-z0-9._]+)', cap):
            mentions[m.lower()] += 1

    return {
        'hashtags_last_90_days':    dict(hashtags.most_common(50)),
        'mentions_last_90_days':    dict(mentions.most_common(50)),
        'posts_analyzed_for_hashtags': recent_count,
        'hashtag_analysis_date_range': f"{fmt_date(now - datetime.timedelta(days=90))} to {fmt_date(now)}",
    }

# ─────────────────────────────────────────────────────────────
#  12. CREATOR PRICING
# ─────────────────────────────────────────────────────────────
PRICING_TABLE = {
    ('UGC Creator',            'Beginner'):    (100,  '3×–6×',  '30K'),
    ('UGC Creator',            'Experienced'): (300,  '5×–9×',  '85K'),
    ('Social Media Influencer','1K–10K'):      (150,  '6×–10×', '165K'),
    ('Social Media Influencer','10K–50K'):     (500,  '6×–10×', '300K'),
    ('Social Media Influencer','50K–500K'):    (2500, '4×–7×',  '1M'),
    ('Social Media Influencer','500K+'):       (4000, '3×–6×',  '3.2M'),
}

def creator_pricing(ui: dict, posts: List[dict]) -> dict:
    u         = ui.get('data', {}).get('user', {}) or {}
    followers = safe_int(u.get('follower_count'))
    bio       = (u.get('biography', '') or '').lower()
    name      = (u.get('full_name', '') or '').lower()
    username  = (u.get('username', '') or '').lower()

    ugc_kw = ['ugc', 'ugc creator', 'user generated', 'content creator', 'brand creator']
    is_ugc = any(k in ' '.join([bio, name, username]) for k in ugc_kw)
    if not is_ugc:
        for n in posts:
            cap = ((n.get('caption') or {}).get('text', '') or '').lower()
            if any(k in cap for k in ugc_kw):
                is_ugc = True
                break

    creator_type = 'UGC Creator' if is_ugc else 'Social Media Influencer'
    if creator_type == 'Social Media Influencer' and followers < 1000:
        creator_type = 'UGC Creator'

    if creator_type == 'UGC Creator':
        tier = 'Experienced' if followers >= 1000 else 'Beginner'
    else:
        tier = ('1K–10K'   if followers < 10_000  else
                '10K–50K'  if followers < 50_000  else
                '50K–500K' if followers < 500_000 else '500K+')

    key = (creator_type, tier)
    base, roi, impressions = PRICING_TABLE.get(key, (100, 'N/A', 'N/A'))

    return {
        'creator_type': creator_type,
        'tier':         tier,
        'pricing': {
            'estimated_roi':          roi,
            'impressions_visibility': impressions,
            'time_15_seconds':        round(base * 0.4),
            'time_30_seconds':        round(base * 0.6),
            'time_60_seconds':        base,
            'time_1_to_5_minutes':    round(base * 1.333),
            'time_greater_5_minutes': round(base * 2),
            'story_usd':              round(base * 0.3),
            'carousel_usd':           round(base * 0.8),
        }
    }

# ─────────────────────────────────────────────────────────────
#  13. ARCHETYPE
# ─────────────────────────────────────────────────────────────
def infer_archetype(niche: str, content_dna: dict, brand_data: dict, engage: dict) -> dict:
    fmt      = content_dna.get('dominant_format', '')
    er       = safe_float(engage.get('avg_er_weighted'))
    collabs  = brand_data.get('total_unique_brands', 0)
    cap_style= content_dna.get('caption_style', '')

    if 'Reel' in fmt and er >= 3:
        archetype = 'The Video Storyteller'
        desc = 'Creates engaging short-form video content with strong audience pull.'
    elif collabs >= 5 and brand_data.get('is_brand_active'):
        archetype = 'The Brand Collaborator'
        desc = 'Actively partners with brands — a proven fit for sponsored content.'
    elif 'Carousel' in fmt and 'Long-form' in cap_style:
        archetype = 'The Educator / Thought Leader'
        desc = 'Uses carousels and detailed captions to inform and teach audiences.'
    elif niche in ['Spirituality', 'Photography']:
        archetype = 'The Cultural Documenter'
        desc = 'Captures cultural, spiritual, or artistic moments with authenticity.'
    elif niche in ['Fashion & Style', 'Beauty']:
        archetype = 'The Aesthetic Creator'
        desc = 'Curates a visually cohesive feed focused on style and beauty.'
    elif niche in ['Travel', 'Nature']:
        archetype = 'The Explorer'
        desc = 'Documents adventures and places — appeals to wanderlust audiences.'
    elif niche in ['Fitness', 'Health & Wellness']:
        archetype = 'The Wellness Advocate'
        desc = 'Motivates and inspires through health and fitness content.'
    elif niche in ['Comedy', 'Entertainment']:
        archetype = 'The Entertainer'
        desc = 'Generates high engagement through humor and entertainment.'
    elif niche in ['Music', 'Dance', 'Art & Design']:
        archetype = 'The Creative Artist'
        desc = 'Shares artistic talent through music, dance, or visual art.'
    elif niche == 'Food':
        archetype = 'The Foodie'
        desc = 'Engages food lovers with culinary content and restaurant experiences.'
    else:
        archetype = 'The Lifestyle Creator'
        desc = 'Shares a broad mix of personal life, interests, and daily moments.'

    return {'archetype': archetype, 'description': desc}

# ─────────────────────────────────────────────────────────────
#  14. GROWTH HEALTH SCORE (0–100)
# ─────────────────────────────────────────────────────────────
def growth_health_score(engage: dict, content_dna: dict, brand_data: dict) -> dict:
    er          = min(safe_float(engage.get('avg_er_weighted')), 10)
    consistency = safe_float(content_dna.get('posting_consistency_score', 0))
    collabs     = min(brand_data.get('total_unique_brands', 0), 10)
    viral       = min(engage.get('viral_posts_count', 0), 5)

    er_score     = er * 4
    cons_score   = consistency * 0.30
    collab_score = collabs * 1.5
    viral_score  = viral * 3

    total = round(er_score + cons_score + collab_score + viral_score)
    total = min(total, 100)
    grade = ('A+' if total >= 90 else 'A'  if total >= 80 else
             'B+' if total >= 70 else 'B'  if total >= 60 else
             'C+' if total >= 50 else 'C'  if total >= 40 else 'D')

    return {
        'growth_health_score': total,
        'grade':               grade,
        'breakdown': {
            'engagement_score':  round(er_score, 2),
            'consistency_score': round(cons_score, 2),
            'collab_score':      round(collab_score, 2),
            'viral_score':       round(viral_score, 2),
        }
    }

# ─────────────────────────────────────────────────────────────
#  MASTER ANALYZER
# ─────────────────────────────────────────────────────────────
def analyze_creator(creator_dir: str) -> Optional[dict]:
    ui_path = os.path.join(creator_dir, 'userInfo.json')
    pi_path = os.path.join(creator_dir, 'postInfo.json')

    if not os.path.exists(ui_path) or not os.path.exists(pi_path):
        print(f"{Fore.RED}  Missing files in {creator_dir}{Style.RESET_ALL}")
        return None

    ui    = load_json(ui_path)
    pi    = load_json(pi_path)
    posts = get_posts(pi)

    if not ui:
        print(f"{Fore.RED}  Empty userInfo{Style.RESET_ALL}")
        return None

    profile  = basic_profile(ui)
    username = profile['username']
    followers= profile['follower_count']

    if not posts:
        print(f"{Fore.YELLOW}  No posts — profile-only entry{Style.RESET_ALL}")

    contacts   = extract_contacts(ui)
    gender     = detect_gender(ui)
    niche      = detect_niche(ui, posts)
    content    = analyze_content_dna(posts)
    engage     = analyze_engagement(posts, followers)
    brands     = analyze_brands(posts, username)
    location   = analyze_locations(posts)
    captions   = analyze_captions(posts)
    hm         = extract_hashtags_mentions(posts)
    pricing    = creator_pricing(ui, posts)
    archetype  = infer_archetype(niche['primary_niche'], content, brands, engage)
    health     = growth_health_score(engage, content, brands)
    full_posts = extract_full_posts(posts, username)

    # Find latest post
    all_taken = [p['taken_at'] for p in full_posts if p.get('taken_at')]
    all_taken.sort()
    latest_ts = all_taken[-1] if all_taken else None
    latest_code = full_posts[-1]['code'] if full_posts else ''
    latest_url  = f'https://www.instagram.com/p/{latest_code}' if latest_code else ''

    # Profile image metadata
    img_url = profile['profile_pic_url']
    img_ext = 'png' if '.png' in (img_url or '') else 'jpg'

    # UGC examples from brand posts
    ugc_examples = ' | '.join([p.get('url', '') for p in brands.get('paid_post_examples', [])
                                 + brands.get('ad_post_examples', [])][:5])

    scraped_ts = os.path.getctime(creator_dir)
    scraped_dt = datetime.datetime.fromtimestamp(scraped_ts).strftime('%Y-%m-%d')

    return {
        # ── Identity ────────────────────────────────────────────
        'username':                  username,
        'full_name':                 profile['full_name'],
        'first_name':                profile['first_name'],
        'last_name':                 profile['last_name'],
        'biography':                 profile['biography'],
        'pk':                        profile['pk'],
        'fbid_v2':                   profile['fbid_v2'],
        'account_type':              profile['account_type'],

        # ── Status flags ────────────────────────────────────────
        'is_verified':               profile['is_verified'],
        'is_business':               profile['is_business'],
        'is_private':                profile['is_private'],
        'is_professional_account':   profile['is_professional_account'],
        'is_unpublished':            profile['is_unpublished'],
        'is_memorialized':           profile['is_memorialized'],
        'is_coppa_enforced':         profile['is_coppa_enforced'],
        'is_regulated_c18':          profile['is_regulated_c18'],
        'is_ring_creator':           profile['is_ring_creator'],
        'is_embeds_disabled':        profile['is_embeds_disabled'],
        'is_cannes':                 profile['is_cannes'],
        'show_ring_award':           profile['show_ring_award'],
        'show_text_post_app_badge':  profile['show_text_post_app_badge'],
        'remove_message_entrypoint': profile['remove_message_entrypoint'],
        'hide_creator_marketplace_badge': profile['hide_creator_marketplace_badge'],
        'has_chaining':              profile['has_chaining'],

        # ── Audience ────────────────────────────────────────────
        'follower_count':            followers,
        'following_count':           profile['following_count'],
        'media_count':               profile['media_count'],
        'total_clips_count':         profile['total_clips_count'],
        'ff_ratio':                  profile['ff_ratio'],
        'creator_size':              profile['creator_size'],

        # ── Contact ─────────────────────────────────────────────
        'email':                     contacts['email'],
        'phone_number':              contacts['phone'],
        'social_links':              contacts['social_links'],
        'parsed_bio_links':          contacts['parsed_links'],
        'raw_bio_links':             contacts['raw_links'],
        'profile_picture_url':       profile['profile_pic_url'],
        'profile_picture_local':     profile['profile_pic_local'],
        'profile_pic_format':        img_ext,
        'has_profile_pic':           profile['has_profile_pic'],
        'external_url':              profile['external_url'],
        'external_lynx_url':         profile['external_lynx_url'],

        # ── Category ─────────────────────────────────────────────
        'category':                  profile['category'],
        'should_show_category':      profile['should_show_category'],

        # ── Account extras ──────────────────────────────────────
        'address_street':            profile['address_street'],
        'city_name':                 profile['city_name'],
        'zip':                       profile['zip'],
        'ai_agent_type':             profile['ai_agent_type'],
        'transparency_label':        profile['transparency_label'],
        'transparency_product':      profile['transparency_product'],
        'latest_reel_media':         profile['latest_reel_media'],
        'latest_besties_reel_media': profile['latest_besties_reel_media'],
        'has_story_archive':         profile['has_story_archive'],
        'reel_media_seen_timestamp': profile['reel_media_seen_timestamp'],

        # ── Viewer/Friendship status ─────────────────────────────
        'friendship_status':         profile['friendship'],

        # ── Gender ──────────────────────────────────────────────
        'gender':                    gender,

        # ── Niche & Archetype ────────────────────────────────────
        'primary_niche':             niche['primary_niche'],
        'niche_distribution':        niche['niche_distribution'],
        'niche_matched_keywords':    niche['matched_keywords'],
        'top_hashtags_overall':      niche['top_hashtags_overall'],
        'hashtag_count_total':       niche['hashtag_count_total'],
        'unique_hashtags_total':     niche['unique_hashtags'],
        'creator_archetype':         archetype['archetype'],
        'archetype_description':     archetype['description'],

        # ── Content DNA ─────────────────────────────────────────
        'content_dna':               content,

        # ── Engagement ──────────────────────────────────────────
        'avg_likes':                 engage.get('avg_likes'),
        'avg_comments':              engage.get('avg_comments'),
        'avg_er_weighted':           engage.get('avg_er_weighted'),
        'avg_er_simple':             engage.get('avg_er_simple'),
        'avg_er_top6':               engage.get('avg_er_top6'),
        'avg_er_last_90_days':       engage.get('avg_er_last_90_days'),
        'er_grade':                  engage.get('er_grade'),
        'audience_engagement_type':  engage.get('audience_engagement_type'),
        'total_likes_all_posts':     engage.get('total_likes_all_posts'),
        'total_comments_all_posts':  engage.get('total_comments_all_posts'),
        'viral_posts_count':         engage.get('viral_posts_count'),
        'viral_posts':               engage.get('viral_posts'),
        'top6_posts':                engage.get('top6_posts'),
        'recent_posts_90d':          engage.get('recent_posts_90d'),
        'all_post_metrics':          engage.get('all_post_metrics'),

        # ── Brands & Collabs ────────────────────────────────────
        'collaboration_status':      brands['collaboration_status'],
        'is_brand_active':           brands['is_brand_active'],
        'paid_partnership_posts':    brands['paid_partnership_posts'],
        'ad_tagged_posts':           brands['ad_tagged_posts'],
        'total_unique_brands':       brands['total_unique_brands'],
        'top_brands':                brands['top_brands'],
        'brand_frequency':           brands['brand_frequency'],
        'total_collaborations':      len(brands['top_brands']),
        'recent_collaborations':     sum(1 for b in brands['top_brands'] if b.get('recent')),
        'ugc_examples':              ugc_examples,

        # ── Location ────────────────────────────────────────────
        'primary_location_name':     location['primary_location'],
        'primary_lat':               location['primary_lat'],
        'primary_lng':               location['primary_lng'],
        'address_city':              location.get('primary_city'),
        'address_state':             location.get('primary_state'),
        'address_country':           location.get('primary_country'),
        'posts_with_location':       location['posts_with_location'],
        'unique_locations':          location['unique_locations'],
        'location_frequency':        location['location_frequency'],
        'is_traveler':               location['is_traveler'],
        'unique_coords_count':       location['unique_coords_count'],
        'all_locations':             location['all_locations'],

        # ── Caption Intelligence ─────────────────────────────────
        'caption_intelligence':      captions,

        # ── Hashtags & Mentions (90d) ────────────────────────────
        'hashtags_last_90_days':     hm['hashtags_last_90_days'],
        'mentions_last_90_days':     hm['mentions_last_90_days'],
        'posts_analyzed_for_hashtags': hm['posts_analyzed_for_hashtags'],
        'hashtag_analysis_date_range': hm['hashtag_analysis_date_range'],

        # ── Pricing ─────────────────────────────────────────────
        'creator_type':              pricing['creator_type'],
        'tier':                      pricing['tier'],
        'creator_pricing_metrics':   pricing['pricing'],

        # ── Health Score ─────────────────────────────────────────
        'growth_health_score':       health['growth_health_score'],
        'health_grade':              health['grade'],
        'health_breakdown':          health['breakdown'],

        # ── Full Posts (ALL data points) ─────────────────────────
        'posts':                     full_posts,

        # ── Totals ───────────────────────────────────────────────
        'total_posts_scraped':       len(full_posts),
        'total_posts_last_3_months': content.get('total_posts_analyzed', 0),

        # ── Latest post ──────────────────────────────────────────
        'latest_post_date':          latest_ts,
        'latest_post_link':          latest_url,

        # ── Meta ─────────────────────────────────────────────────
        'analyzed_date':             datetime.datetime.now().strftime('%Y-%m-%d'),
        'scraped_date':              scraped_dt,
    }

# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
def main():
    print(f"\n{Fore.CYAN}{'═'*68}")
    print(f"  Instagram Creator Analyzer v3.0 — FULL DATA CAPTURE")
    print(f"{'═'*68}{Style.RESET_ALL}\n")

    base = base_path = os.path.join(os.getcwd(), 'data', 'output')
    if not os.path.exists(base):
        print(f"{Fore.RED}No 'output/' directory found.{Style.RESET_ALL}")
        return

    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
        try:
            with open(csv_path, 'r') as f:
                targets = {r['username'].strip() for r in csv.DictReader(f) if r.get('username')}
        except Exception as e:
            print(f"{Fore.RED}CSV error: {e}{Style.RESET_ALL}")
            return
        folders = [f for f in os.listdir(base) if f in targets]
        print(f"{Fore.CYAN}CSV mode: {len(folders)} matching folders{Style.RESET_ALL}\n")
    else:
        folders = [f for f in os.listdir(base) if os.path.isdir(os.path.join(base, f))]
        print(f"{Fore.CYAN}Analyzing {len(folders)} creators in output/{Style.RESET_ALL}\n")

    results, ok, fail = [], 0, 0

    for i, folder in enumerate(sorted(folders), 1):
        path = os.path.join(base, folder)
        if not os.path.isdir(path):
            continue
        print(f"{Fore.GREEN}[{i}/{len(folders)}] {folder}{Style.RESET_ALL}")
        r = analyze_creator(path)
        if r:
            ok += 1
            results.append(r)
            print(f"  Followers: {r['follower_count']:,}  |  ER: {r['avg_er_weighted']}%  |  "
                  f"Score: {r['growth_health_score']}/100 ({r['health_grade']})")
            print(f"  Niche: {r['primary_niche']}  |  Archetype: {r['creator_archetype']}")
            print(f"  Format: {r['content_dna'].get('dominant_format','?')}  |  "
                  f"Posts: {r['total_posts_scraped']}  |  "
                  f"Activity: {r['content_dna'].get('activity_status','?')}")
            if r['primary_location_name']:
                print(f"  Location: {r['primary_location_name']}")
        else:
            fail += 1
            print(f"  {Fore.RED}Failed{Style.RESET_ALL}")
        print()

    if not results:
        print(f"{Fore.RED}No results generated.{Style.RESET_ALL}")
        return

    results_sorted = sorted(results, key=lambda x: x.get('growth_health_score', 0), reverse=True)
    avg_er_all = round(safe_div(sum(r.get('avg_er_weighted', 0) or 0 for r in results), len(results)), 3)

    print(f"\n{Fore.CYAN}{'═'*68}")
    print(f"  SUMMARY:  Processed {ok+fail}  |  Success: {ok}  |  Failed: {fail}")
    print(f"  Avg ER:   {avg_er_all}%")
    if results:
        best = results_sorted[0]
        print(f"  Top creator: {best['username']} ({best['growth_health_score']}/100)")
    print(f"{'═'*68}{Style.RESET_ALL}")

    output = {
        'generated_at':       datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_analyzed':     ok,
        'summary': {
            'avg_er':          avg_er_all,
            'top_niches':      dict(Counter(r['primary_niche'] for r in results if r.get('primary_niche')).most_common(10)),
            'archetypes':      dict(Counter(r['creator_archetype'] for r in results).most_common()),
            'avg_health_score': round(safe_div(sum(r.get('growth_health_score', 0) for r in results), max(len(results), 1))),
            'brand_active_count': sum(1 for r in results if r.get('is_brand_active')),
            'locations_found': sum(1 for r in results if r.get('primary_location_name')),
            'gender_breakdown': dict(Counter(r.get('gender', 'Unknown') for r in results).most_common()),
            'creator_type_breakdown': dict(Counter(r.get('creator_type', '') for r in results).most_common()),
        },
        'creators': results_sorted,
    }

    os.makedirs(os.path.join(os.getcwd(), 'data'), exist_ok=True)
    out_path = os.path.join(os.getcwd(), 'data', 'analyzed.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n{Fore.GREEN}✓ Saved → {out_path}  ({len(results)} creators){Style.RESET_ALL}")


if __name__ == '__main__':
    main()