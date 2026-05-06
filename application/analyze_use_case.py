"""Use-case: analyze a directory of scraped creators -> streaming analyzed.json.

Supports parallel execution via ProcessPoolExecutor (default) and a fully
deterministic sequential fallback used by tests / in-memory adapters.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Iterable, List, Optional, Set, Tuple

from ..adapters.repositories.file_repository import FileCreatorRepository
from ..domain.services.analyzer import analyze
from ..domain.services.exclusions import ExclusionRules


def _analyze_one(base_dir: str, username: str) -> Optional[dict]:
    repo = FileCreatorRepository(base_dir)
    raw = repo.load(username)
    if not raw:
        return None
    res = analyze(raw)
    return res.as_dict() if res else None


def _why_excluded(d: dict, rules: Optional[ExclusionRules]) -> Optional[str]:
    """Return a short reason string if `d` should be excluded, else None."""
    if not rules:
        return None
    u = (d.get("username") or "").lower()
    if u in rules.usernames:
        return "username_in_denylist"
    if any(s and s in u for s in rules.username_substrings):
        return "username_matched_substring"
    if any(r.search(u) for r in rules.username_regexes):
        return "username_matched_regex"
    bio = (d.get("biography") or "").lower()
    if bio and any(s and s in bio for s in rules.bio_substrings):
        return "bio_matched_substring"
    fc = d.get("follower_count") or 0
    if rules.min_followers is not None and fc < rules.min_followers:
        return "below_min_followers"
    if rules.max_followers is not None and fc > rules.max_followers:
        return "above_max_followers"
    mc = d.get("media_count")
    if rules.require_posts and mc is not None and mc <= 0:
        return "no_posts"
    return None


def _write_envelope(path: str, results: List[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "analysis_date": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "creators": results,
                "total_creators_analyzed": len(results),
            },
            f, indent=2, ensure_ascii=False,
        )


def run_analyze(
    base_dir: str,
    output_path: str = "analyzed.json",
    only_usernames: Optional[Iterable[str]] = None,
    exclude_usernames: Optional[Set[str]] = None,
    max_workers: int = 2,
    rules: Optional[ExclusionRules] = None,
    repository: Optional[Any] = None,
    parallel: bool = True,
) -> Tuple[int, int, Counter]:
    """Analyze creators.

    Returns (ok, failed, reasons_counter).

    - When ``repository`` is provided (e.g. ``InMemoryRepository``), or when
      ``parallel`` is False, or ``max_workers <= 1``, runs sequentially.
    - Otherwise fans out across processes (ProcessPoolExecutor).
    """
    repo = repository or FileCreatorRepository(
        base_dir, exclude=exclude_usernames or set(),
    )
    all_existing = set(repo.list_usernames())
    if only_usernames:
        targets = [u for u in only_usernames if u in all_existing]
    else:
        targets = sorted(all_existing)

    reasons: Counter = Counter()
    results: List[dict] = []
    failed = 0

    if not targets:
        _write_envelope(output_path, [])
        return 0, 0, reasons

    use_parallel = (
        parallel and repository is None and max_workers > 1
    )

    def _consume(d: Optional[dict], username: str) -> None:
        nonlocal failed
        if not d:
            failed += 1
            reasons["analyzer_returned_none"] += 1
            return
        why = _why_excluded(d, rules)
        if why:
            failed += 1
            reasons[why] += 1
            return
        results.append(d)

    if not use_parallel:
        for u in targets:
            raw = repo.load(u)
            res = analyze(raw) if raw else None
            d = res.as_dict() if res else None
            _consume(d, u)
    else:
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_analyze_one, base_dir, u): u for u in targets}
            for fut in as_completed(futures):
                u = futures[fut]
                try:
                    d = fut.result()
                except Exception:
                    d = None
                _consume(d, u)

    _write_envelope(output_path, results)
    return len(results), failed, reasons


def load_usernames_csv(path: str, col: str = "username") -> list[str]:
    import csv
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        key = next((c for c in reader.fieldnames if c.lower() == col), None)
        if not key:
            return []
        for row in reader:
            v = (row.get(key) or "").strip()
            if v:
                out.append(v)
    return out


def load_exclude_csv(path: str, col: str = "username") -> set[str]:
    return {u.lower() for u in load_usernames_csv(path, col)}
