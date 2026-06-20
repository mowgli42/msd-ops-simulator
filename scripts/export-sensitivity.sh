#!/usr/bin/env bash
# Export sensitivity sweep CSV (stations grid by default).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements-dev.txt
fi
MODE="${1:-stations}"
OUT="${2:-output/sensitivity-${MODE}.csv}"
.venv/bin/python -m analysis.sensitivity --config fixtures/baseline.yaml --mode "$MODE" -o "$OUT"
echo "Open in Excel/LibreOffice: $OUT"
