"""Use-case: scrape a list of profile URLs."""
from __future__ import annotations
from typing import Iterable

from ..adapters.scrapers.selenium_scraper import (
    SeleniumInstagramScraper, ScraperConfig, load_urls_from_csv,
)


def run_scrape(urls: Iterable[str], config: ScraperConfig) -> int:
    scraper = SeleniumInstagramScraper(config)
    results = list(scraper.scrape_many(urls))
    return len(results)


__all__ = ["run_scrape", "ScraperConfig", "load_urls_from_csv"]
