"""Richer exclusion rules.

Supports username denylists, substring patterns, regex patterns, and a set
of built-in heuristics (e.g. obvious spam/bot/news/giveaway accounts) so the
analyzer pipeline can prune noise before exporting.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Set

# Built-in keyword fragments commonly seen in low-value / non-creator accounts.
DEFAULT_BAD_USERNAME_FRAGMENTS = [
    "giveaway", "official_news", "buyfollowers", "freefollow",
    "promo_bot", "spam", "casino", "viagra", ".onlyfans",
]

# Built-in fragments suggesting brand/news accounts rather than creators.
DEFAULT_BAD_BIO_FRAGMENTS = [
    "for promotions dm", "buy followers", "earn money fast",
    "official news account", "press inquiries only",
]


@dataclass
class ExclusionRules:
    usernames: Set[str] = field(default_factory=set)
    username_substrings: List[str] = field(default_factory=list)
    username_regexes: List[re.Pattern] = field(default_factory=list)
    bio_substrings: List[str] = field(default_factory=list)
    min_followers: Optional[int] = None
    max_followers: Optional[int] = None
    require_posts: bool = True
    use_defaults: bool = True

    def __post_init__(self) -> None:
        self.usernames = {u.lower() for u in self.usernames}
        self.username_substrings = [s.lower() for s in self.username_substrings]
        self.bio_substrings = [s.lower() for s in self.bio_substrings]
        if self.use_defaults:
            self.username_substrings.extend(DEFAULT_BAD_USERNAME_FRAGMENTS)
            self.bio_substrings.extend(DEFAULT_BAD_BIO_FRAGMENTS)

    # ---- High-level checks ------------------------------------------------

    def excludes_username(self, username: str) -> bool:
        if not username:
            return True
        u = username.lower()
        if u in self.usernames:
            return True
        if any(s and s in u for s in self.username_substrings):
            return True
        if any(r.search(u) for r in self.username_regexes):
            return True
        return False

    def excludes_profile(
        self,
        username: str,
        biography: Optional[str] = None,
        follower_count: Optional[int] = None,
        media_count: Optional[int] = None,
    ) -> bool:
        if self.excludes_username(username):
            return True
        if biography:
            bl = biography.lower()
            if any(s and s in bl for s in self.bio_substrings):
                return True
        if self.min_followers is not None and (follower_count or 0) < self.min_followers:
            return True
        if self.max_followers is not None and (follower_count or 0) > self.max_followers:
            return True
        if self.require_posts and (media_count is not None) and media_count <= 0:
            return True
        return False


def build_rules(
    excluded_usernames: Optional[Iterable[str]] = None,
    substrings: Optional[Iterable[str]] = None,
    regexes: Optional[Iterable[str]] = None,
    bio_substrings: Optional[Iterable[str]] = None,
    min_followers: Optional[int] = None,
    max_followers: Optional[int] = None,
    use_defaults: bool = True,
) -> ExclusionRules:
    return ExclusionRules(
        usernames=set(excluded_usernames or []),
        username_substrings=list(substrings or []),
        username_regexes=[re.compile(p, re.IGNORECASE) for p in (regexes or [])],
        bio_substrings=list(bio_substrings or []),
        min_followers=min_followers,
        max_followers=max_followers,
        use_defaults=use_defaults,
    )
