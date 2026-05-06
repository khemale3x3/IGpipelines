"""Generates a short, human-readable summary report next to the CSV/JSON.

Reports:
  * counts: analyzed ok / failed / total
  * filter reasons (which exclusion rule pruned each profile)
  * top locations (city / country)
  * exclusions applied (the rule config used)
"""
from __future__ import annotations
import json
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..domain.services.exclusions import ExclusionRules


@dataclass
class SummaryStats:
    analyzed_ok: int = 0
    analyzed_failed: int = 0
    filter_reasons: Counter = field(default_factory=Counter)
    top_cities: List[tuple] = field(default_factory=list)
    top_countries: List[tuple] = field(default_factory=list)
    exclusions_applied: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "analyzed_ok": self.analyzed_ok,
            "analyzed_failed": self.analyzed_failed,
            "total": self.analyzed_ok + self.analyzed_failed,
            "filter_reasons": dict(self.filter_reasons),
            "top_cities": self.top_cities,
            "top_countries": self.top_countries,
            "exclusions_applied": self.exclusions_applied,
        }

    def format_text(self) -> str:
        lines = [
            "=== Pipeline Summary ===",
            f"Analyzed OK:     {self.analyzed_ok}",
            f"Filtered/failed: {self.analyzed_failed}",
            f"Total examined:  {self.analyzed_ok + self.analyzed_failed}",
            "",
            "Filter reasons:",
        ]
        if self.filter_reasons:
            for reason, n in self.filter_reasons.most_common():
                lines.append(f"  - {reason}: {n}")
        else:
            lines.append("  (none)")
        lines += ["", "Top cities:"]
        lines += [f"  - {c}: {n}" for c, n in self.top_cities] or ["  (none)"]
        lines += ["", "Top countries:"]
        lines += [f"  - {c}: {n}" for c, n in self.top_countries] or ["  (none)"]
        lines += ["", "Exclusions applied:"]
        for k, v in (self.exclusions_applied or {}).items():
            lines.append(f"  - {k}: {v}")
        return "\n".join(lines) + "\n"


def rules_to_dict(rules: Optional[ExclusionRules]) -> Dict[str, Any]:
    if not rules:
        return {}
    return {
        "explicit_usernames": sorted(rules.usernames),
        "username_substrings": rules.username_substrings,
        "username_regexes": [r.pattern for r in rules.username_regexes],
        "bio_substrings": rules.bio_substrings,
        "min_followers": rules.min_followers,
        "max_followers": rules.max_followers,
        "use_defaults": rules.use_defaults,
    }


def compute_top_locations(creators: List[dict], n: int = 10):
    cities = Counter(
        (c.get("address_city") or "").strip()
        for c in creators if (c.get("address_city") or "").strip()
    )
    countries = Counter(
        (c.get("address_country") or "").strip()
        for c in creators if (c.get("address_country") or "").strip()
    )
    return cities.most_common(n), countries.most_common(n)


def write_summary(
    stats: SummaryStats,
    out_dir: str,
    base_name: str = "summary",
) -> Dict[str, str]:
    """Write summary.txt + summary.json next to the report. Returns paths."""
    os.makedirs(out_dir or ".", exist_ok=True)
    txt = os.path.join(out_dir or ".", base_name + ".txt")
    js = os.path.join(out_dir or ".", base_name + ".json")
    with open(txt, "w", encoding="utf-8") as f:
        f.write(stats.format_text())
    with open(js, "w", encoding="utf-8") as f:
        json.dump(stats.as_dict(), f, indent=2, ensure_ascii=False)
    return {"text": txt, "json": js}
