"""Extract email + phone from biography."""
from __future__ import annotations
import re
from typing import Any, Dict, Optional
from ._shapes import user_data

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_PATTERNS = [
    r"\+?\d{1,4}[-.\s]?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{4}",
    r"\+\d{10,15}",
    r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
    r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\s*x\d{1,5}",
    r"\d{3,}[-.\s]?\d{3,}[-.\s]?\d{4,}",
]


def extract_email(user_info: Dict[str, Any]) -> Optional[str]:
    bio = user_data(user_info).get("biography") or ""
    m = _EMAIL_RE.findall(bio)
    return m[0] if m else None


def extract_phone(user_info: Dict[str, Any]) -> Optional[str]:
    bio = user_data(user_info).get("biography") or ""
    for pat in _PHONE_PATTERNS:
        m = re.search(pat, bio)
        if m:
            return re.sub(r"[\s.\-]", "", m.group(0)).strip()
    return None
