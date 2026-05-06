"""In-memory mock adapters — used by tests so we never touch Selenium."""
from __future__ import annotations
from typing import Dict, Iterable, List, Optional

from ..domain.models import RawCreatorData


class InMemoryRepository:
    """Mirror of FileCreatorRepository backed by a dict."""

    def __init__(self, data: Optional[Dict[str, RawCreatorData]] = None,
                 exclude: Optional[set] = None) -> None:
        self._data: Dict[str, RawCreatorData] = data or {}
        self._exclude = {u.lower() for u in (exclude or set())}

    def add(self, username: str, raw: RawCreatorData) -> None:
        self._data[username] = raw

    def list_usernames(self) -> List[str]:
        return [u for u in self._data if u.lower() not in self._exclude]

    def load(self, username: str) -> Optional[RawCreatorData]:
        return self._data.get(username)


class FakeScraper:
    """Deterministic scraper: returns canned RawCreatorData per URL."""

    def __init__(self, by_url: Dict[str, RawCreatorData]) -> None:
        self._by_url = by_url

    def scrape(self, url: str) -> Optional[RawCreatorData]:
        return self._by_url.get(url)

    def scrape_many(self, urls: Iterable[str]) -> List[RawCreatorData]:
        out = []
        for u in urls:
            r = self.scrape(u)
            if r is not None:
                out.append(r)
        return out
