#!/usr/bin/env bash
# Run capacity model unit tests (stdlib only).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 -m pytest tests/ -q
