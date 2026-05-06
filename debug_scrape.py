#!/usr/bin/env python3
"""Debug helper: run a single-profile scrape and print network logs/page content.
"""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Ensure package imports resolve (make parent dir importable so
# `insta_pipeline.adapters...` works and relative imports inside modules succeed).
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from insta_pipeline.adapters.scrapers.selenium_scraper import (
    load_urls_from_csv,
    ScraperConfig,
    SeleniumInstagramScraper,
    _configure_driver,
    _get_network_responses,
)


def get_sessions():
    s = os.getenv("IG_SESSION_IDS", "")
    return [x.strip() for x in s.split(",") if x.strip()]


def main():
    sessions = get_sessions()
    print("Sessions found:", len(sessions))
    urls = load_urls_from_csv("data/input.csv")
    if not urls:
        print("No URLs found in data/input.csv")
        return
    url = urls[0]
    print("Testing URL:", url)

    cfg = ScraperConfig(session_ids=sessions or [None], max_workers=1, headless=False, output_dir="output", max_scrolls=1, test_mode=True)

    # High-level scrape via adapter
    try:
        s = SeleniumInstagramScraper(cfg)
        result = s.scrape(url)
        print("Adapter scrape returned:", bool(result))
        if result and result.user_info:
            print("User info keys:", list(result.user_info.keys())[:10])
    except Exception as e:
        print("Adapter scrape error:", e)

    # Low-level driver inspection
    try:
        driver = _configure_driver(sessions[0] if sessions else None, headless=False)
        driver.get(url)
        time.sleep(4)
        print("Page title:", driver.title)
        logs = _get_network_responses(driver)
        print("Performance log entries:", len(logs))
        for i, entry in enumerate(logs[:50]):
            try:
                params = entry.get("params", {})
                resp = params.get("response", {})
                rurl = resp.get("url") or ""
                if not rurl:
                    continue
                print(i, rurl[:200])
                if ("graphql" in rurl) or ("/ajax/" in rurl) or ("__a=1" in rurl) or ("/api/v1/" in rurl):
                    rid = params.get("requestId") or resp.get("requestId")
                    try:
                        body_raw = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": rid})
                        body = body_raw.get("body", "")
                        print("-- BODY SNIPPET:", (body[:1000] if isinstance(body, str) else str(body))[:1000])
                    except Exception as e:
                        print("-- Failed to get body for", rurl, e)
                    break
            except Exception:
                print(i, "<unreadable>")
        # print first 1000 chars of page source for quick inspection
        print("Page source snippet:", driver.page_source[:1000].replace('\n',' ')[:1000])
    except Exception as e:
        print("Driver inspection error:", e)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
