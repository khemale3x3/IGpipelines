#!/usr/bin/env bash
# Helper script: quick commands to run the insta_pipeline project
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./scripts/commands.sh <cmd>

Commands:
  setup        Create venv and install dependencies
  test         Run pytest
  export-sample Export CSV from data/analyzed_sample.json
  analyze-sample Analyze `data/output_sample` into analyzed JSON
  export-from-analyzed Export CSV from a given analyzed JSON
  run-pipeline Run full pipeline (requires IG sessions and ChromeDriver)

Examples:
  ./scripts/commands.sh setup
  ./scripts/commands.sh test
  ./scripts/commands.sh export-sample
EOF
}

case "${1-}" in
  setup)
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ;;
  test)
    source .venv/bin/activate || true
    pytest -q
    ;;
  export-sample)
    python main.py export --analyzed data/analyzed_sample.json --csv data/exported_from_sample.csv --ssa data/unique_names_ssa.txt
    ;;
  analyze-sample)
    python main.py analyze --output-dir data/output_sample --analyzed data/analyzed_from_output.json
    ;;
  export-from-analyzed)
    if [ -z "${2-}" ]; then
      echo "Usage: $0 export-from-analyzed <analyzed.json>"
      exit 2
    fi
    python main.py export --analyzed "$2" --csv "${2%.json}.csv" --ssa data/unique_names_ssa.txt
    ;;
  run-pipeline)
    if [ -z "${IG_SESSION_IDS-}" ]; then
      echo "Set IG_SESSION_IDS env var (comma-separated sessionid values) before running."
      exit 2
    fi
    python main.py run --scrape --input data/input_sample.csv --output-dir output --analyzed analyzed.json --csv report.csv --ssa data/unique_names_ssa.txt
    ;;
  *)
    usage
    exit 1
    ;;
esac
