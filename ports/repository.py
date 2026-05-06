"""Port: source of raw creator data (file system, S3, DB, etc.)."""
from __future__ import annotations
from typing import Iterable, Optional, Protocol
from ..domain.models import RawCreatorData


class CreatorRepositoryPort(Protocol):
    def list_usernames(self) -> Iterable[str]: ...
    def load(self, username: str) -> Optional[RawCreatorData]: ...
