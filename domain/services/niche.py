"""Weighted multi-source niche identification.

Adapted from analyze_insta.py — uses phrase + token matching across bio,
username, full_name and recent post captions, with per-source weights.
"""
from __future__ import annotations
import re
from typing import Any, Dict, List
from ._shapes import user_data, caption_text

NICHE_CATEGORIES: Dict[str, List[str]] = {
    "Fashion & Beauty": [
        "ootd", "style", "fashion", "skincare", "mua", "makeup", "beauty",
        "outfit", "apparel", "grwm", "lookbook", "wardrobe", "clothing",
        "couture", "accessories", "hairstyle", "nails", "cosmetics",
        "streetstyle", "fashionista", "skincareroutine", "makeuptutorial",
        "kbeauty", "fashionweek", "streetwear", "sneakerhead",
        "thrifted", "ethicalfashion", "cleanbeauty", "crueltyfree",
        "veganbeauty", "fragrance", "jewelryaddict", "hairstylist",
        "balayage", "manicure", "nailart", "selfcare", "luxuryfashion",
        "designerwear", "capsulewardrobe", "minimaliststyle", "bohostyle",
        "chic", "glam", "modeling", "fashionphotography", "vogue",
        "beautytips", "morningroutine", "quietluxury", "oldmoney",
        "beautyinfluencer", "sephora", "ulta", "lipstick", "contour",
        "highlighter", "foundation", "facemask", "sunscreen", "spf",
    ],
    "Fitness & Wellness": [
        "workout", "gymlife", "fitness", "personaltrainer", "wellness",
        "healthylifestyle", "bodybuilding", "yoga", "hiit", "mealprep",
        "fitfam", "transformation", "nutrition", "weightloss", "holistic",
        "meditation", "physique", "fit", "fitnessjourney", "activewear",
        "athleisure", "crossfit", "powerlifting", "calisthenics", "pilates",
        "mindfulness", "mentalhealth", "selflove", "recovery", "stretching",
        "mobility", "cardio", "running", "marathon", "swimming",
        "gymmotivation", "fitnessgoals", "shredded", "abs", "muscle",
        "supplements", "protein", "creatine", "macros", "intermittentfasting",
        "keto", "paleo", "plantbased", "veganfitness", "vegetarian",
        "healthyeating", "smoothie", "superfood", "biohacking", "longevity",
        "guthealth", "probiotics", "vitamins", "deadlift", "squat",
        "benchpress", "homegym", "homeworkout", "fitnesscoach",
        "wellnesscoach", "endurance", "strengthtraining", "ironman",
    ],
    "Travel": [
        "wanderlust", "travel", "digitalnomad", "bucketlist", "explore",
        "solotravel", "staycation", "adventure", "roadtrip", "travelgram",
        "travelblogger", "globetrotter", "passportready", "boutiquehotel",
        "resort", "beachvibes", "mountains", "hiking", "backpacking",
        "vanlife", "glamping", "cabinlife", "cityscape", "sunsethunter",
        "travelhacks", "traveldiaries", "tourist", "localguide",
        "hiddengems", "expats", "livingabroad", "remotework", "coworking",
        "workation", "itinerary", "traveltips", "packwithme",
        "carryononly", "slowtravel", "luxuryresort", "yachtlife",
        "ecotourism", "sustainabletravel", "nationalparks",
        "trekking", "scubadiving", "stargazing", "islandhopping", "jetset",
        "travelgoals",
    ],
    "Lifestyle": [
        "lifestyle", "vlog", "dailyvlog", "aesthetic", "minimalist",
        "homedecor", "luxurylifestyle", "minimalism", "organizing",
        "decluttering", "homemakeover", "renovation", "diyhome", "plants",
        "urbanjungle", "gardening", "homestead", "cottagecore",
        "darkacademia", "slowliving", "weekendgetaway", "brunch",
        "coffeeaddict", "latteart", "cafeculture", "journaling",
        "plannersetup", "productivity", "aestheticlife", "moodboard",
        "contentcreator", "influencerlife", "dayinthelife", "ditl",
        "photodump", "lifestyleblogger", "visionboard", "manifesting",
        "goodvibes", "gratitude", "dailyroutine", "selfimprovement",
        "personalgrowth", "adulting", "cleangirl", "softaesthetic",
        "dreamhome", "midcenturymodern", "cozyhome", "smarthome",
        "intentionalliving", "habitstacking", "unboxing", "haul",
        "weeklyreset", "sundayreset", "cleantok",
    ],
    "Food & Cooking": [
        "foodie", "instafood", "recipe", "chef", "homecooking", "vegan",
        "keto", "plantbased", "mukbang", "foodphotography", "baking",
        "pastry", "streetfood", "foodreview", "culinary", "brunch",
        "dinnerideas", "gastronomy", "delicious", "yummy", "foodstagram",
        "foodblogger", "foodlover", "foodgasm", "foodgram", "foodpics",
        "homechef", "cookingathome", "healthyfood", "homemade",
        "kitchen", "restaurant", "bar", "cocktail", "mixology", "wine",
        "beer", "brewery", "coffee", "espresso", "latte", "sweets",
        "dessert", "chocolate", "cheese", "seafood", "grill", "bbq",
        "spicy", "organic", "farmtotable", "gourmet", "tasting", "menu",
        "mealprep", "diet", "nutrition", "smoothies", "juicing",
        "fermentation", "sourdough", "groceryhaul", "farmersmarket",
        "comfortfood", "cleaneating", "glutenfree", "dairyfree",
    ],
    "Tech & Gadgets": [
        "tech", "gadget", "setup", "review", "software", "coding",
        "innovation", "unboxing", "android", "windows", "linux", "hardware",
        "cpu", "gpu", "nvidia", "intel", "amd", "mechanicalkeyboard",
        "desksetup", "battlestation", "custompc", "cybersecurity",
        "programming", "python", "javascript", "developer", "engineer",
        "devlife", "opensource", "github", "robotics", "drones",
        "smarthome", "alexa", "googlehome", "futuretech", "space",
        "spacex", "nasa", "science", "biotech", "renewableenergy", "ev",
        "tesla", "electricvehicle", "saas", "cloudcomputing", "aws",
        "azure", "googlecloud", "machinelearning", "deeplearning",
        "chatgpt", "midjourney", "generativeai", "llm", "promptengineering",
        "appreview", "techtips", "productivitytools", "notion",
    ],
    "Gaming & eSports": [
        "gaming", "esports", "gamer", "streaming", "pcgaming", "twitch",
        "discord", "gameplay", "razer", "logitech", "console",
        "playstation", "xbox", "nintendo", "switch", "vr", "valorant",
        "fortnite", "roblox", "minecraft", "speedrun", "cosplay",
        "gamingcommunity", "tournament", "proplayer", "battleroyale",
        "mmo", "indiegames", "gamingmemes",
    ],
    "Personal Finance": [
        "entrepreneur", "startup", "investing", "stocks", "forex",
        "ecommerce", "marketing", "sidehustle", "passiveincome",
        "realestate", "financialfreedom", "wealth", "trading", "mentor",
        "businessowner", "successmindset", "finance", "money", "budgeting",
        "savings", "debtfree", "financialliteracy", "personalfinance",
        "bitcoin", "ethereum", "blockchain", "web3", "dropshipping",
        "shopify", "digitalmarketing", "seo", "copywriting", "branding",
        "sales", "emailmarketing", "affiliatemarketing", "founder", "ceo",
        "leadership", "venturecapital", "freelancing", "solopreneur",
        "millionaire", "dividends", "indexfunds", "retirement",
    ],
    "Art / DIY": [
        "artist", "illustration", "digitalart", "procreate", "crafts",
        "handmade", "diy", "painting", "sketchbook", "creative", "tutorial",
        "design", "graphicdesign", "calligraphy", "embroidery", "knitting",
        "artwork", "drawing", "painter", "sculpture", "ceramics", "pottery",
        "printmaking", "photography", "videography", "animation", "3dart",
        "characterdesign", "conceptart", "watercolor", "acrylic",
        "oilpainting", "abstractart", "fineart", "gallery", "studio",
        "mural", "graffiti", "streetart", "scrapbooking", "crochet",
        "sewing", "quilting", "fashiondesign", "interiordesign", "origami",
        "typography", "logo", "uxui", "webdesign", "motiongraphics",
    ],
    "Education / Skill": [
        "studygram", "careertips", "mentorship", "productivity",
        "softskills", "tutorial", "learning", "knowledge", "certification",
        "workshop", "upskilling", "internship", "jobsearch",
        "resumebuilding", "education", "student", "university", "college",
        "school", "teacher", "professor", "academic", "research",
        "scholarship", "onlinelearning", "edtech", "elearning",
        "skillshare", "coursera", "udemy", "careercoach",
        "careerdevelopment", "studymotivation", "stem", "datascience",
        "selftaught", "lifelonglearning", "personaldevelopment",
    ],
    "Pet Products": [
        "petparent", "dogmom", "dogdad", "catlady", "furparent",
        "petinfluencer", "pet", "dog", "cat", "petblogger",
        "rescuedad", "rescuemom", "adventuredog", "petgrooming",
        "doggear", "dogtraining", "puppytraining", "pethacks",
        "dogfriendlytravel", "petwellness", "dogsofinstagram",
        "catsoftiktok", "furbaby", "barkbox",
    ],
    "Family & Parenting": [
        "parenting", "momlife", "dadlife", "familyvlog", "gentleparenting",
        "positiveparenting", "toddlermom", "boymom", "girlmom",
        "newborncare", "pregnancyannouncement", "babyessentials",
        "parentingtips", "parenthacks", "familytravel", "homeschooling",
        "sahm", "workingmom", "workingdad", "blendedfamily", "coparenting",
        "fosterparent", "sensoryplay", "earlylearning",
        "babyledweaning", "blw", "pottytraining", "montessoriathome",
        "milestones", "familytraditions", "parentingwin",
        "honestmotherhood", "fatherhood", "motherhoodunplugged",
        "familygoals", "intentionalparenting", "nurserydecor",
        "babyregistry", "toddlerfashion", "kidsstyle", "firsttimemom",
    ],
}

_SOURCE_WEIGHTS = {
    "biography": 2.0, "username": 2.5, "full_name": 1.5, "captions": 1.2,
}

_MULTI = {kw for v in NICHE_CATEGORIES.values() for kw in v if " " in kw}
_SINGLE = {kw for v in NICHE_CATEGORIES.values() for kw in v if " " not in kw}


def _clean(text: str) -> str:
    if not text:
        return ""
    return " ".join(re.sub(r"[^a-zA-Z0-9\s]", "", text.lower()).split())


def identify_niche(user_info: Dict[str, Any], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    u = user_data(user_info)
    sources = {
        "biography": _clean(u.get("biography", "")),
        "username": _clean(u.get("username", "")),
        "full_name": _clean(u.get("full_name", "")),
        "captions": " ".join(_clean(caption_text(p.get("node", {}))) for p in posts),
    }

    scores: Dict[str, float] = {c: 0.0 for c in NICHE_CATEGORIES}
    matched = set()

    for src, text in sources.items():
        if not text:
            continue
        w = _SOURCE_WEIGHTS[src]
        # Phrase matches
        for phrase in _MULTI:
            if phrase in text:
                matched.add(phrase)
                for cat, kws in NICHE_CATEGORIES.items():
                    if phrase in kws:
                        scores[cat] += w * 1.5
        # Token matches via set intersection
        tokens = set(text.split())
        found = tokens & _SINGLE
        for tok in found:
            matched.add(tok)
            for cat, kws in NICHE_CATEGORIES.items():
                if tok in kws:
                    scores[cat] += w

    total = sum(scores.values()) or 1.0
    distribution = {
        k: round((v / total) * 100, 1) for k, v in scores.items() if v > 0
    }
    sorted_n = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    winner, top = sorted_n[0] if sorted_n else ("Others", 0.0)
    confidence = "High" if top > 8 else "Medium" if top > 3 else "Low"

    return {
        "overall_niche": winner if top > 0 else "Others",
        "confidence_level": confidence,
        "distribution": distribution,
        "matched_keywords": sorted(matched),
        "top_score": round(top, 2),
    }
