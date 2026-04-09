#!/usr/bin/env bash
# Build "SSH Term.app" with PyInstaller, then wrap it in a .pkg that installs
# into /Applications/. Unsigned: Gatekeeper may require right-click → Open once.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-0.1.0}"
APP_NAME="SSH Term"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -U pip -q
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt -q

rm -rf build dist
.venv/bin/pyinstaller -y \
  --windowed \
  --name "$APP_NAME" \
  --osx-bundle-identifier sh.sshterm.manager \
  --add-data "assets:assets" \
  --collect-submodules pynput \
  --hidden-import iterm_ssh \
  --hidden-import storage \
  --hidden-import global_hotkey \
  --hidden-import macos_dock \
  --hidden-import macos_reopen \
  --hidden-import AppKit \
  --collect-submodules objc \
  main.py

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/Applications"
cp -R "dist/$APP_NAME.app" "$STAGE/Applications/"
PKG_BASENAME="SSH-Term-${VERSION}.pkg"
pkgbuild \
  --root "$STAGE" \
  --identifier "sh.sshterm.pkg" \
  --version "$VERSION" \
  --install-location "/" \
  "dist/$PKG_BASENAME"

echo "Built: dist/$APP_NAME.app"
echo "Installer: dist/$PKG_BASENAME"
