"""Port: validates and normalizes a first name (e.g. against SSA names list)."""
from __future__ import annotations
from typing import Protocol


class FirstNameValidatorPort(Protocol):
    def normalize(self, first_name: str, fallback_username: str) -> str: ...
