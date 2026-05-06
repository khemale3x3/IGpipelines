"""Split full_name into first_name + last_name."""
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
from ._shapes import user_data


def extract_names(user_info: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    full = (user_data(user_info).get("full_name") or "").strip()
    parts = full.split()
    first = parts[0] if parts else None
    last = " ".join(parts[1:]) if len(parts) > 1 else None
    return first, last
