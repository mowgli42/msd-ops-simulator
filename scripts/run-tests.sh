#!/usr/bin/env bash
# Run unit tests. Creates .venv and installs dev deps if needed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements-dev.txt
.venv/bin/python scripts/sync-config.py
.venv/bin/python -m pytest tests/ -q
