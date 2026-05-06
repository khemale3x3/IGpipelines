"""Compatibility wrapper exposing a `SeleniumInstagramScraper` class backed by
`adapters.scrapers.scraper` procedural implementation.
"""
from typing import Iterable, Generator, List
from .scraper import (
    ScraperConfig,
    configure_driver,
    scrape_profile,
    save_data,
    get_next_session_id,
)


def load_urls_from_csv(path: str):
    """Read CSV and return list of URLs (fallback to csv module if pandas missing)."""
    try:
        import pandas as pd
        df = pd.read_csv(path)
        return df['url'].dropna().astype(str).tolist()
    except Exception:
        urls = []
        import csv
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for r in reader:
                u = r.get('url') or ''
                if u:
                    urls.append(u)
        return urls


class SeleniumInstagramScraper:
    def __init__(self, config: ScraperConfig):
        self.config = config

    def scrape_many(self, urls: Iterable[str]) -> Generator[bool, None, None]:
        """Simple sequential scraper generator for compatibility.
        Yields True/False per URL indicating whether data was saved.
        """
        # single driver instance for this run
        driver = None
        try:
            for url in urls:
                session_id = get_next_session_id(self.config)
                driver = configure_driver(session_id, self.config)
                if not driver:
                    yield False
                    continue

                username = url.strip().rstrip('/').split('/')[-1]
                data = scrape_profile(driver, url, self.config)
                ok = save_data(username, data, url, [], {
                    "failed": 0,
                    "saved": 0,
                    "pictures_downloaded": 0,
                    "posts_saved": 0,
                    "locations_found": 0,
                }, [], self.config)
                yield bool(ok)
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass


__all__ = ["SeleniumInstagramScraper", "ScraperConfig", "load_urls_from_csv"]
