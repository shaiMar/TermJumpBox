#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python main.py
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 main.py
fi

echo "No Python found. Create a venv: cd \"$SCRIPT_DIR\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
exit 1
