# Architecture Overview

This repository is a small Instagram scraping + analysis pipeline. Files and folders:
- adapters/
  - scrapers/scraper.py: Canonical headless Selenium scraper (multi-session, threaded).
  - selenium_scraper.py: Compatibility wrapper exposing `SeleniumInstagramScraper` API.
- application/
  - scrape_use_case.py, analyze_use_case.py, export_use_case.py: high-level use-cases orchestrating scraping, analysis, and export.

- tools/
  - finalanalyzer_full.py: Analyzer that scans `data/output/<username>/` folders and writes `data/analyzed.json`.
  - csv_maker.py: Converts `data/analyzed.json` into `data/output_YYYYMMDD.csv`.
- data/
  - input.csv: input list of profile URLs (default `data/input.csv`).
  - inputdone.csv: completed URLs (default `data/inputdone.csv`).
- main.py: CLI entrypoint that wires `.env` settings and runs use-cases.
- requirements.txt: Python dependencies (e.g. selenium, python-dotenv, tqdm).
- README.md: Usage examples and run commands.
Notes:
- All I/O is centralized under `data/` to avoid ambiguity.
- Use `.env` to control `DEFAULT_INPUT`, `DEFAULT_DONE`, `DEFAULT_HEADLESS`, `IG_SESSION_IDS`, `DEFAULT_WORKERS`, and `DEFAULT_OUTPUT_DIR`.
- To analyze results: run `python tools/finalanalyzer_full.py` then `python tools/csv_maker.py`.
# insta_pipeline — Architecture Overview

This document explains the repository layout, the role of each folder/file, and provides the main commands to run and test the project.

Project summary
- Purpose: Scrape Instagram profiles (optional via Selenium), analyze scraped JSON into structured records, and export results to CSV/JSON.

Top-level layout
- `main.py`: CLI entrypoint. Commands: `scrape`, `analyze`, `export`, `all`, `run`.
- `requirements.txt`: Python dependencies.
- `data/`: example input/output files (sample CSVs, SSA names, sample analyzed JSON and sample scraped output).

Key folders
- `adapters/` — external-system adapters (concrete implementations):
  - `scrapers/selenium_scraper.py`: Selenium-based scraper, implements scraping, saving `userInfo.json` and `postInfo.json` per username.
  - `exporters/streaming_csv_exporter.py`: Streams `analyzed.json` -> CSV using `ijson`.
  - `name_providers/ssa_name_provider.py`: Optional SSA name validator, falls back to passthrough.
  - `mocks.py`: lightweight test adapters (for tests).

- `application/` — Use-cases (orchestrators):
  - `scrape_use_case.py`: Loads URLs from CSV and runs scraper adapter.
  - `csv_validation.py`: Validates input CSV format before scraping.
  - `analyze_use_case.py`: Loads raw scraped directories, runs analysis, writes `analyzed.json`.
  - `export_use_case.py`: Wraps exporter to create CSV from `analyzed.json`.
  - `pipeline_use_case.py`: Top-level pipeline orchestration (scrape -> analyze -> export).
  - `summary_report.py`, `csv_validation.py`: helper utilities for reporting & validation.

- `domain/` — Pure domain logic and models:
  - `models.py`: dataclasses for `RawCreatorData` and `AnalyzedCreator`.
  - `services/`: analysis modules (e.g. `analyzer.py`, `hashtags.py`, `locations.py`, `pricing.py`) that compute the final analyzed records.

- `ports/` — small adapter interfaces (ports) that define the expected behaviour of adapters (exporter, scraper, repository, name_provider).

- `adapters/repositories/file_repository.py` — Filesystem repository; expects layout:
  - `base_dir/<username>/userInfo.json` and `postInfo.json`.

- `tests/` — pytest tests and fixtures. Example: `tests/fixtures.py` contains sample CSV and raw JSON used by tests.

Data expectations and sample files
- Scrape input CSV: header `url` and rows like `https://www.instagram.com/<handle>/`.
- Usernames CSV: header `username` (used by `analyze --usernames`).
- Exclude CSV: header `username` (used by `--exclude`).
- `analyzed.json`: produced by `analyze` use-case; appears under the path given by `--analyzed`.
- Optional SSA names file: `unique_names_ssa.txt` (one name per line or CSV style `NAME,count`) used by the SSA name validator.

Important runtime notes
- Scraping requires `selenium`, a compatible Chrome/Chromium and ChromeDriver installed and available in PATH. Also you must provide valid Instagram session IDs (cookie `sessionid`) via `--sessions` or environment `IG_SESSION_IDS`.
- Analysis and export require only the `ijson` dependency (streaming JSON parser).

Commands (setup & run)

1) Create venv & install dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2) Run tests
```bash
pytest -q
```

3) Quick export test (no scraping required)
You can either run the package as a module from the *parent* directory:
```bash
# from the directory that contains the `insta_pipeline` folder
python -m insta_pipeline.main export --analyzed data/analyzed_sample.json --csv data/exported_from_sample.csv --ssa data/unique_names_ssa.txt
```
Or when you're inside the `insta_pipeline` project root, run the script directly:
```bash
python main.py export --analyzed data/analyzed_sample.json --csv data/exported_from_sample.csv --ssa data/unique_names_ssa.txt
```

4) Analyze a prepared scraped output directory
```bash
python -m insta_pipeline.main analyze \
  --output-dir data/output_sample \
  --analyzed data/analyzed_from_output.json

python -m insta_pipeline.main export \
  --analyzed data/analyzed_from_output.json \
  --csv data/exported_from_output.csv \
  --ssa data/unique_names_ssa.txt
```

5) Run full pipeline (Scrape -> Analyze -> Export) — requires sessions and ChromeDriver
Run from the package parent directory:
```bash
export IG_SESSION_IDS="SESSIONID1,SESSIONID2"
python -m insta_pipeline.main run --scrape --input data/input_sample.csv --output-dir output --analyzed analyzed.json --csv report.csv --ssa data/unique_names_ssa.txt
```
Or run from inside the project root using the script directly:
```bash
export IG_SESSION_IDS="SESSIONID1,SESSIONID2"
python main.py run --scrape --input data/input_sample.csv --output-dir output --analyzed analyzed.json --csv report.csv --ssa data/unique_names_ssa.txt
```

Tip: if you prefer to import `insta_pipeline` as a module with `-m` while inside the project, install it editable:
```bash
pip install -e .
# or create a minimal pyproject/setup to allow editable install
```

6) Run only scraping
```bash
python -m insta_pipeline.main scrape --input data/input_sample.csv --sessions "SESSIONID1,SESSIONID2" --output-dir output
```

7) Run only analyze from an existing `output` dir
```bash
python -m insta_pipeline.main analyze --output-dir output --analyzed analyzed.json
```

8) Run only export from an existing analyzed.json
```bash
python -m insta_pipeline.main export --analyzed analyzed.json --csv report.csv --ssa data/unique_names_ssa.txt
```

Files of interest (quick pointers)
- `main.py`: CLI wiring and argument defaults.
- `application/csv_validation.py`: validates the `input.csv` format before scraping.
- `adapters/scrapers/selenium_scraper.py`: `load_urls_from_csv()` reads CSVs and `SeleniumInstagramScraper` saves per-user JSON under `output_dir/<username>/`.
- `adapters/exporters/streaming_csv_exporter.py`: uses `ijson` to stream `analyzed.json` and write CSV rows defined by `HEADERS`.

If you'd like I can:
- Commit `ARCHITECTURE.md` to the repo (already created),
- Add a short `README_RUN.md` with copy-paste commands tuned to your environment,
- Or run `python -m insta_pipeline.main analyze` + `export` locally now and show the generated CSV (I can run them if you want me to). 

---
Generated: 2026-05-05
