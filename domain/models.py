"""Pure domain models. No I/O, no framework deps."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RawCreatorData:
    """Raw scraped JSON for a single creator."""
    user_info: Dict[str, Any]
    post_info: Dict[str, Any]
    scraped_timestamp: Optional[float] = None  # epoch seconds


@dataclass
class AnalyzedCreator:
    """Result of analyzing one creator. Serializable to dict."""
    data: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return dict(self.data)
