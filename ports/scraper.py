"""Port: scraper that turns a profile URL into RawCreatorData."""
from __future__ import annotations
from typing import Iterable, Protocol
from ..domain.models import RawCreatorData


class ScraperPort(Protocol):
    def scrape(self, url: str) -> RawCreatorData | None: ...
    def scrape_many(self, urls: Iterable[str]) -> Iterable[RawCreatorData]: ...
