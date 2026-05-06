"""SSA names-list adapter that validates first names against a known set.

Falls back to "@<username>" when not a 100% match (mirrors jsontocsv.py).
"""
from __future__ import annotations
import os
import re


class SSAFirstNameValidator:
    def __init__(self, ssa_path: str = "unique_names_ssa.txt") -> None:
        self.valid: set[str] = set()
        if os.path.exists(ssa_path):
            with open(ssa_path, "r", encoding="utf-8") as f:
                for line in f:
                    name = line.strip().split(",")[0].upper()
                    if name:
                        self.valid.add(name)

    def normalize(self, first_name: str, fallback_username: str) -> str:
        if not first_name or not self.valid:
            return f"@{fallback_username}" if fallback_username else ""
        clean = re.sub(r"[^a-zA-Z]", "", first_name).strip()
        if not clean:
            return f"@{fallback_username}"
        formatted = clean.capitalize()
        if formatted.upper() in self.valid:
            return formatted
        return f"@{fallback_username}"


class PassthroughFirstNameValidator:
    """No-op; returns the original name (useful when SSA file is missing)."""

    def normalize(self, first_name: str, fallback_username: str) -> str:
        return first_name or (f"@{fallback_username}" if fallback_username else "")
