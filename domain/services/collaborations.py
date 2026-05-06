"""Brand collaborations & UGC examples (merged from analyze_insta + finalanalyzer)."""
from __future__ import annotations
import datetime as dt
import re
from typing import Any, Dict, List, Optional
from ._shapes import caption_text

_STOP = {
    "the", "and", "for", "from", "with", "this", "that", "have", "has", "her",
    "his", "our", "my", "your", "their", "its", "as", "at", "by", "to", "in",
    "on", "of", "or", "if",
}


def _owner_username(posts: List[Dict[str, Any]]) -> Optional[str]:
    if not posts:
        return None
    try:
        node = (posts[0] or {}).get("node", {}) or {}
        return ((node.get("user") or {}).get("username")) or None
    except (AttributeError, TypeError, IndexError):
        return None


def _is_recent(taken_at: Optional[int], cutoff: dt.datetime) -> bool:
    if not taken_at:
        return False
    try:
        return dt.datetime.fromtimestamp(taken_at) > cutoff
    except (ValueError, TypeError, OSError):
        return False


def extract_ugc_examples(posts: List[Dict[str, Any]], limit: int = 3) -> str:
    if not posts:
        return ""
    uname = _owner_username(posts)
    codes: List[str] = []

    def _push(code: Optional[str]) -> bool:
        if code and code not in codes and len(codes) < limit:
            codes.append(code)
            return True
        return False

    # 1) paid_partnership clips
    for p in posts:
        node = (p or {}).get("node") or {}
        if node.get("product_type") != "clips":
            continue
        if node.get("is_paid_partnership"):
            _push(node.get("code"))
    # 2) #ad / #collab clips
    if len(codes) < limit:
        for p in posts:
            node = (p or {}).get("node") or {}
            if node.get("product_type") != "clips":
                continue
            cap = caption_text(node).lower()
            if "#ad" in cap or "#collab" in cap:
                _push(node.get("code"))
    # 3) different-owner clips
    if len(codes) < limit and uname:
        for p in posts:
            node = (p or {}).get("node") or {}
            if node.get("product_type") != "clips":
                continue
            owner = (node.get("owner") or {}).get("username")
            if owner and owner != uname:
                _push(node.get("code"))
    # 4) coauthor clips
    if len(codes) < limit and uname:
        for p in posts:
            node = (p or {}).get("node") or {}
            if node.get("product_type") != "clips":
                continue
            for ca in node.get("coauthor_producers") or []:
                if isinstance(ca, dict):
                    cu = ca.get("username")
                    if cu and cu != uname:
                        if _push(node.get("code")):
                            break

    return " | ".join(f"https://www.instagram.com/p/{c}" for c in codes)


def identify_collaborations(posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not posts:
        return {
            "status": None, "total_collaborations": 0, "recent_collaborations": 0,
            "all_collaborations": [], "ugc_examples": "",
        }

    uname = _owner_username(posts)
    recent_cutoff = dt.datetime.now() - dt.timedelta(days=300)
    seen, all_collabs, recent = set(), [], []
    final_status: Optional[str] = None

    def _add(name: str, source: str, is_recent: bool) -> None:
        if not name or len(name) < 3 or name.lower() in _STOP or name in seen:
            return
        seen.add(name)
        all_collabs.append({"name": name, "count": 1, "is_recent": is_recent, "source": source})
        if is_recent:
            recent.append({"name": name, "source": source if source != "owner" else "owner"})

    # Paid partnerships
    for p in posts:
        node = (p or {}).get("node") or {}
        if not node.get("is_paid_partnership"):
            continue
        final_status = "Active"
        is_recent = _is_recent(node.get("taken_at"), recent_cutoff)
        for m in re.findall(r"@([A-Za-z0-9._]+)", caption_text(node)):
            _add(m.rstrip("."), "paid_partnership", is_recent)
        break

    # owners + coauthors
    for p in posts:
        node = (p or {}).get("node") or {}
        is_recent = _is_recent(node.get("taken_at"), recent_cutoff)
        owner = (node.get("owner") or {}).get("username")
        if owner and owner != uname:
            _add(owner, "owner", is_recent)
        for ca in node.get("coauthor_producers") or []:
            if isinstance(ca, dict):
                _add(ca.get("username") or "", "coauthor", is_recent)

    # #ad / #collab fallback for status
    if final_status is None:
        for p in posts:
            node = (p or {}).get("node") or {}
            cap = caption_text(node).lower()
            if "#ad" in cap or "#collab" in cap:
                final_status = "Active"
                is_recent = _is_recent(node.get("taken_at"), recent_cutoff)
                for m in re.findall(r"@([A-Za-z0-9._]+)", caption_text(node)):
                    _add(m.rstrip("."), "tag", is_recent)
                break

    if final_status is None and uname:
        # Any owner / coauthor mismatch implies collab
        for p in posts:
            node = (p or {}).get("node") or {}
            owner = (node.get("owner") or {}).get("username")
            if owner and owner != uname:
                final_status = "Active"
                break
            for ca in node.get("coauthor_producers") or []:
                if isinstance(ca, dict) and ca.get("username") and ca.get("username") != uname:
                    final_status = "Active"
                    break
            if final_status:
                break

    return {
        "status": final_status,
        "total_collaborations": len(all_collabs),
        "recent_collaborations": len(recent),
        "all_collaborations": all_collabs,
        "ugc_examples": extract_ugc_examples(posts),
    }
