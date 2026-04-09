#!/usr/bin/env bash
# Build a real SSH Term.app on the Desktop: exec's Python as the app process (proper
# GUI session). AppleScript / do shell script + nohup breaks WindowServer + global hotkeys.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MAIN_PY="$REPO_ROOT/main.py"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script is intended for macOS." >&2
  exit 1
fi

if [[ ! -f "$MAIN_PY" ]]; then
  echo "main.py not found at $MAIN_PY — is this the sshTerm repo root?" >&2
  exit 1
fi

DESKTOP="${HOME}/Desktop"
if [[ ! -d "$DESKTOP" ]]; then
  echo "Desktop not found: $DESKTOP" >&2
  exit 1
fi

APP="${DESKTOP}/SSH Term.app"
MACOS_DIR="${APP}/Contents/MacOS"
RES_DIR="${APP}/Contents/Resources"
EXE="${MACOS_DIR}/ssh-term-launch"
LEGACY_CMD="${DESKTOP}/SSH Term.command"

rm -rf "$APP"
mkdir -p "$MACOS_DIR" "$RES_DIR"

cat > "${APP}/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>ssh-term-launch</string>
  <key>CFBundleIdentifier</key>
  <string>sh.sshterm.desktop-launcher</string>
  <key>CFBundleName</key>
  <string>SSH Term</string>
  <key>CFBundleDisplayName</key>
  <string>SSH Term</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

{
  echo '#!/bin/bash'
  echo 'set -euo pipefail'
  echo 'export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"'
  printf 'REPO=%q\n' "$REPO_ROOT"
  echo 'cd "$REPO" || { /usr/bin/osascript -e '"'"'display alert "SSH Term" message "Repo folder is missing. Re-run install-desktop-launcher.sh." as critical'"'"' >&2; exit 1; }'
  echo 'if [[ -x .venv/bin/python ]]; then exec .venv/bin/python main.py; fi'
  echo 'if command -v python3 >/dev/null 2>&1; then exec python3 main.py; fi'
  echo '/usr/bin/osascript -e '"'"'display alert "SSH Term" message "No Python found. Create a venv in the repo and pip install -r requirements.txt." as critical'"'"' >&2'
  echo 'exit 1'
} > "$EXE"
chmod +x "$EXE"

rm -f "$LEGACY_CMD"

echo "Created: $APP"
echo "Removed legacy: $LEGACY_CMD (if it existed)."
echo "This app runs Python directly (not launch.sh over do shell script) so the UI and ⌘E can work."
echo "If ⌘E from other apps fails: System Settings → Privacy & Security → Accessibility → enable SSH Term; restart the app once."
