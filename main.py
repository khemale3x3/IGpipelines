"""CLI entry-point.

Usage:
    python -m insta_pipeline.main scrape   --input input.csv
    python -m insta_pipeline.main analyze  --output-dir output --analyzed analyzed.json
    python -m insta_pipeline.main export   --analyzed analyzed.json --csv report.csv
    python -m insta_pipeline.main all      --input input.csv
    python -m insta_pipeline.main run      --input input.csv --csv report.csv --json report.json
"""
from __future__ import annotations
import argparse
import datetime as dt
import os
import sys
if __package__ is None:
    # Allow executing `python main.py` from the package root by making the
    # parent directory importable and setting the package name so relative
    # imports inside this module work as expected.
    pkg_dir = os.path.dirname(__file__)
    parent = os.path.dirname(pkg_dir)
    if parent and parent not in sys.path:
        sys.path.insert(0, parent)
    __package__ = "insta_pipeline"
try:
    # load .env if python-dotenv is installed; silent no-op if not available
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass


def _cmd_scrape(args: argparse.Namespace) -> int:
    from .application.scrape_use_case import (
        run_scrape, ScraperConfig, load_urls_from_csv,
    )
    from .application.csv_validation import validate_input_csv
    rep = validate_input_csv(args.input)
    if not rep.ok:
        print("ERROR: input CSV validation failed")
        print(rep.format())
        return 2
    print(rep.format())
    sessions = [s.strip() for s in (args.sessions or "").split(",") if s.strip()]
    if not sessions:
        sessions = [s for s in os.environ.get("IG_SESSION_IDS", "").split(",") if s]
    if not sessions:
        print("ERROR: provide --sessions or IG_SESSION_IDS env var")
        return 2
    urls = load_urls_from_csv(args.input)
    if not urls:
        print(f"No URLs in {args.input}")
        return 1
    headless_env = os.environ.get("DEFAULT_HEADLESS", "true").lower()
    headless = headless_env in ("1", "true", "yes")
    cfg = ScraperConfig(
        session_ids=sessions, max_workers=args.workers,
        output_dir=args.output_dir, test_mode=args.test,
        input_file=args.input,
        max_test_profiles=args.test_profiles,
        headless=headless,
    )
    n = run_scrape(urls, cfg)
    print(f"Scraped {n} creators into {args.output_dir}/")
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    from .application.analyze_use_case import (
        run_analyze, load_usernames_csv, load_exclude_csv,
    )
    only = load_usernames_csv(args.usernames) if args.usernames else None
    exclude = load_exclude_csv(args.exclude) if args.exclude else set()
    ok, fail, reasons = run_analyze(
        base_dir=args.output_dir, output_path=args.analyzed,
        only_usernames=only, exclude_usernames=exclude,
        max_workers=args.workers,
        parallel=getattr(args, "parallel", True),
    )
    print(f"Analyzed: {ok} ok, {fail} failed -> {args.analyzed}")
    if reasons:
        print("Filter reasons:", dict(reasons))
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    from .application.export_use_case import run_export
    n = run_export(args.analyzed, args.csv, ssa_path=args.ssa)
    print(f"Exported {n} rows -> {args.csv}")
    return 0


def _cmd_all(args: argparse.Namespace) -> int:
    rc = _cmd_scrape(args)
    if rc != 0:
        return rc
    rc = _cmd_analyze(args)
    if rc != 0:
        return rc
    return _cmd_export(args)


def _cmd_run(args: argparse.Namespace) -> int:
    """Unified pipeline: optional scrape, then analyze, then CSV/JSON export."""
    from .application.analyze_use_case import (
        load_usernames_csv, load_exclude_csv,
    )
    from .application.pipeline_use_case import PipelineConfig, run_pipeline
    from .domain.services.exclusions import build_rules

    if args.scrape:
        rc = _cmd_scrape(args)
        if rc != 0:
            return rc

    only = load_usernames_csv(args.usernames) if args.usernames else None
    exclude = load_exclude_csv(args.exclude) if args.exclude else set()
    rules = build_rules(
        excluded_usernames=exclude,
        substrings=[s for s in (args.exclude_substring or []) if s],
        regexes=[r for r in (args.exclude_regex or []) if r],
        bio_substrings=[s for s in (args.exclude_bio or []) if s],
        min_followers=args.min_followers,
        max_followers=args.max_followers,
        use_defaults=not args.no_default_exclusions,
    )
    cfg = PipelineConfig(
        output_dir=args.output_dir,
        analyzed_path=args.analyzed,
        csv_path=args.csv,
        json_path=args.json,
        ssa_path=args.ssa,
        only_usernames=only,
        exclude_usernames=exclude,
        rules=rules,
        max_workers=args.workers,
        parallel=getattr(args, "parallel", True),
    )
    res = run_pipeline(cfg)
    print(
        f"Pipeline done: {res.analyzed_ok} analyzed, {res.analyzed_failed} skipped, "
        f"CSV={res.csv_rows} rows, JSON={res.json_rows} rows"
    )
    print(f"Summary written: {res.summary_paths.get('text')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    today = dt.datetime.now().strftime("%Y%m%d")
    p = argparse.ArgumentParser(prog="insta_pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--output-dir", default=os.environ.get("DEFAULT_OUTPUT_DIR", "output"))
    common.add_argument("--analyzed", default=os.environ.get("DEFAULT_ANALYZED", "analyzed.json"))
    common.add_argument("--csv", default=os.environ.get("DEFAULT_CSV", f"output{today}.csv"))
    common.add_argument("--workers", type=int, default=int(os.environ.get("DEFAULT_WORKERS", "2")))
    common.add_argument("--ssa", default=os.environ.get("DEFAULT_SSA", "unique_names_ssa.txt"))
    common.add_argument(
        "--sequential", dest="parallel", action="store_false",
        help="Disable ProcessPoolExecutor; run analysis sequentially "
             "(useful for tests / debugging).",
    )
    common.set_defaults(parallel=True)

    s = sub.add_parser("scrape", parents=[common])
    s.add_argument("--input", default=os.environ.get("DEFAULT_INPUT", "input.csv"))
    s.add_argument("--sessions", default=os.environ.get("IG_SESSION_IDS", ""))
    s.add_argument("--test", action="store_true")
    s.add_argument("--test-profiles", type=int, default=5)
    s.set_defaults(func=_cmd_scrape)

    a = sub.add_parser("analyze", parents=[common])
    a.add_argument("--usernames", default=None)
    a.add_argument("--exclude", default=None)
    a.set_defaults(func=_cmd_analyze)

    e = sub.add_parser("export", parents=[common])
    e.set_defaults(func=_cmd_export)

    al = sub.add_parser("all", parents=[common])
    al.add_argument("--input", default=os.environ.get("DEFAULT_INPUT", "input.csv"))
    al.add_argument("--sessions", default=os.environ.get("IG_SESSION_IDS", ""))
    al.add_argument("--test", action="store_true")
    al.add_argument("--test-profiles", type=int, default=5)
    al.add_argument("--usernames", default=None)
    al.add_argument("--exclude", default=None)
    al.set_defaults(func=_cmd_all)

    r = sub.add_parser("run", parents=[common],
                       help="Single-step pipeline (optional scrape + analyze + export)")
    r.add_argument("--input", default=os.environ.get("DEFAULT_INPUT", "input.csv"))
    r.add_argument("--sessions", default=os.environ.get("IG_SESSION_IDS", ""))
    r.add_argument("--scrape", action="store_true",
                   help="Also run the scrape step before analyzing")
    r.add_argument("--test", action="store_true")
    r.add_argument("--test-profiles", type=int, default=5)
    r.add_argument("--usernames", default=None)
    r.add_argument("--exclude", default=None)
    r.add_argument("--json", default=None, help="Optional JSON output path")
    r.add_argument("--exclude-substring", action="append", default=[])
    r.add_argument("--exclude-regex", action="append", default=[])
    r.add_argument("--exclude-bio", action="append", default=[])
    r.add_argument("--min-followers", type=int, default=None)
    r.add_argument("--max-followers", type=int, default=None)
    r.add_argument("--no-default-exclusions", action="store_true")
    r.set_defaults(func=_cmd_run)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
