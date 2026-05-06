# Instagram Creator Intelligence Pipeline (Hexagonal Architecture)

Unified Python pipeline that **scrapes Instagram creators**, **deeply analyzes**
them (profile, posts, niche, pricing, collaborations, locations, hashtags), and
**exports CSV / JSON** plus a **summary report** — built with **Ports &
Adapters (Hexagonal)** architecture so every layer is testable.

This single project replaces and merges:

- `insta_main.py` / `iteration01scraper.py`  → Selenium scraping adapter
- `analyze_insta*.py` / `finalanalyzer.py`   → Deep domain analysis
- `jsontocsv*.py`                            → Streaming CSV/JSON exporter

---

## Architecture

```
insta_pipeline/
├── domain/                 # Pure business rules (no I/O)
│   ├── models.py
│   └── services/
│       ├── basic_info.py / gender.py / social_links.py / contact.py
│       ├── names.py / creator_size.py / niche.py
│       ├── collaborations.py / engagement.py / hashtags.py
│       ├── locations.py    (deep, country/state/zip inference)
│       ├── pricing.py      (tier-based pricing matrix)
│       ├── exclusions.py   (denylists, regex, follower thresholds)
│       └── analyzer.py     (orchestrator)
├── ports/                  # Interfaces (Protocols)
│   ├── scraper.py / repository.py / exporter.py / name_provider.py
├── adapters/               # Concrete implementations
│   ├── scrapers/selenium_scraper.py
│   ├── repositories/file_repository.py
│   ├── exporters/{streaming_csv_exporter,json_exporter}.py
│   ├── name_providers/ssa_name_provider.py
│   └── mocks.py            (InMemoryRepository, FakeScraper for tests)
├── application/            # Use-cases wiring ports + domain
│   ├── scrape_use_case.py
│   ├── analyze_use_case.py
│   ├── export_use_case.py
│   ├── pipeline_use_case.py
│   ├── csv_validation.py   (input CSV checks)
│   └── summary_report.py   (counts/reasons/top locations)
├── tests/
│   ├── fixtures.py
│   ├── test_domain.py
│   ├── test_exclusions.py
│   ├── test_locations.py
│   ├── test_pipeline.py
│   └── test_validation_and_summary.py
├── main.py                 # CLI: scrape | analyze | export | all | run
└── requirements.txt
```

---

## Install

```bash
pip install -r insta_pipeline/requirements.txt
```

---

## CLI — copy-paste examples

> Run from the directory **containing** `insta_pipeline/`.

### 1. Validate + scrape an input CSV

`input.csv` must have a header row with a `url` column:

```csv
url
https://www.instagram.com/jane_doe/
https://www.instagram.com/london_chef/
```

```bash
python -m insta_pipeline.main scrape \
    --input input.csv \
    --sessions "SESSIONID_1,SESSIONID_2" \
    --output-dir output \
    --workers 4
```

The scraper validates the CSV first and exits with a clear error if anything
is malformed (missing `url` column, invalid Instagram URLs, duplicates, etc.).

You can also pass sessions via env var:

```bash
export IG_SESSION_IDS="SESSIONID_1,SESSIONID_2"
python -m insta_pipeline.main scrape --input input.csv --output-dir output
```

### 2. Analyze scraped creators

Parallel (default — uses `ProcessPoolExecutor`):

```bash
python -m insta_pipeline.main analyze \
    --output-dir output \
    --analyzed analyzed.json \
    --workers 4
```

Sequential fallback (deterministic, used by tests / debugging):

```bash
python -m insta_pipeline.main analyze \
    --output-dir output --analyzed analyzed.json --sequential
```

Restrict to a subset, or exclude usernames:

```bash
python -m insta_pipeline.main analyze \
    --output-dir output --analyzed analyzed.json \
    --usernames usernames.csv --exclude exclude.csv
```

### 3. Export to CSV

```bash
python -m insta_pipeline.main export \
    --analyzed analyzed.json \
    --csv report.csv \
    --ssa unique_names_ssa.txt
```

### 4. Unified `run` command — scrape (optional) + analyze + CSV/JSON + summary

Analyze + export only (no scraping):

```bash
python -m insta_pipeline.main run \
    --output-dir output \
    --analyzed analyzed.json \
    --csv report.csv \
    --json report.json
```

Full one-shot pipeline including scraping, with rich exclusion rules:

```bash
python -m insta_pipeline.main run \
    --scrape \
    --input input.csv \
    --sessions "SESSIONID_1,SESSIONID_2" \
    --output-dir output \
    --analyzed analyzed.json \
    --csv report.csv \
    --json report.json \
    --workers 4 \
    --min-followers 1000 \
    --max-followers 5000000 \
    --exclude-substring "promo" --exclude-substring "giveaway" \
    --exclude-regex "^bot[_0-9]+$" \
    --exclude-bio "buy followers" \
    --exclude exclude.csv
```

Force sequential (e.g. inside CI):

```bash
python -m insta_pipeline.main run --sequential \
    --output-dir output --csv report.csv --json report.json
```

### Summary report

After `run`, two files are written next to your CSV/JSON:

- `summary.txt` — human-readable
- `summary.json` — machine-readable

They contain:

- counts (analyzed OK / failed / total)
- filter reasons (e.g. `below_min_followers`, `username_matched_substring`)
- top cities and countries
- the exact exclusion config that was applied

---

## Tests

```bash
PYTHONPATH=. python -m pytest insta_pipeline/tests/ -v
```

All tests use the `InMemoryRepository` / `FakeScraper` mock adapters and
fixtures in `tests/fixtures.py` — **no Selenium and no network access required.**

---

## Key flags reference

| Flag                         | Default          | Meaning                                              |
|------------------------------|------------------|------------------------------------------------------|
| `--input`                    | `input.csv`      | Input CSV with `url` column                          |
| `--output-dir`               | `output`         | Where scraped raw JSON is read/written               |
| `--analyzed`                 | `analyzed.json`  | Path to the analyzed envelope JSON                   |
| `--csv`                      | `outputYYYYMMDD.csv` | CSV report path                                  |
| `--json`                     | *(unset)*        | Optional JSON report path (`run` command)            |
| `--ssa`                      | `unique_names_ssa.txt` | SSA first-name validator file (optional)        |
| `--workers`                  | `2`              | Pool size for scrape / analyze                       |
| `--sequential`               | off              | Disable `ProcessPoolExecutor`; run in one process    |
| `--scrape`                   | off              | (`run`) also scrape before analyzing                 |
| `--sessions`                 | env              | Comma-separated Instagram session IDs                |
| `--min-followers` / `--max-followers` | unset   | Numeric thresholds                                   |
| `--exclude-substring`        | repeatable       | Username substring filter                            |
| `--exclude-regex`            | repeatable       | Username regex filter                                |
| `--exclude-bio`              | repeatable       | Bio substring filter                                 |
| `--no-default-exclusions`    | off              | Disable built-in spam/bot heuristics                 |


----
.venv/bin/python main.py scrape --input data/input.csv --output-dir data/output

.venv/bin/python tools/finalanalyzer.py

 .venv/bin/python tools/csv_maker.py  
