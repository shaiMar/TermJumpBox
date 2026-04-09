#!/usr/bin/env bash
set -euo pipefail

# Start the GUI detached from this terminal so your shell prompt returns right away.
# Logs: ~/.config/ssh-term/launch.log
# Foreground (blocks terminal, for debugging): SSH_TERM_FG=1 ./launch.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ "${SSH_TERM_FG:-}" == 1 ]]; then
  if [[ -x .venv/bin/python ]]; then
    exec .venv/bin/python main.py
  fi
  if command -v python3 >/dev/null 2>&1; then
    exec python3 main.py
  fi
  echo "No Python found. Create a venv: cd \"$SCRIPT_DIR\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

run_detached() {
  local py="$1"
  local log_dir="${HOME}/.config/ssh-term"
  mkdir -p "$log_dir"
  nohup "$py" main.py >>"${log_dir}/launch.log" 2>&1 &
  disown &>/dev/null || true
}

if [[ -x .venv/bin/python ]]; then
  run_detached .venv/bin/python
  exit 0
fi

if command -v python3 >/dev/null 2>&1; then
  run_detached python3
  exit 0
fi

echo "No Python found. Create a venv: cd \"$SCRIPT_DIR\" && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
exit 1
