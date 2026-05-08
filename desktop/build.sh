#!/usr/bin/env bash
# build.sh — bash equivalent of build.ps1 for macOS / Linux users.
#
# Usage:
#   ./build.sh                 # build for current OS only
#   ./build.sh win             # Windows .exe installer (works from Mac/Linux)
#   ./build.sh mac             # Mac .dmg (must be run on macOS for signed builds)
#   ./build.sh all             # build everything this machine can produce

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND="$REPO_ROOT/frontend"
DESKTOP="$SCRIPT_DIR"
BACKEND_URL="http://127.0.0.1:8001"

step() { printf "\n\033[36m==> %s\033[0m\n" "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: '$1' not on PATH. $2"; exit 1; }; }

step "Pre-flight checks"
need node "Install Node.js 20+ from https://nodejs.org"
need yarn "Run: npm install -g yarn"
# Python is bundled via python-build-standalone — no longer a host requirement.
echo "  node   : $(node --version)"
echo "  yarn   : $(yarn --version)"
echo "  python : (will be bundled)"

uname_s=$(uname -s)
case "$uname_s" in
  Darwin) HOST="mac" ;;
  Linux)  HOST="linux" ;;
  MINGW*|MSYS*|CYGWIN*) HOST="win" ;;
  *) HOST="linux" ;;
esac

TARGET="${1:-current}"
case "$TARGET" in
  current) TARGETS=("$HOST") ;;
  all)
    if [ "$HOST" = "mac" ]; then TARGETS=("mac" "win" "linux")
    elif [ "$HOST" = "win" ]; then TARGETS=("win" "linux"); echo "WARNING: Mac build skipped — use macOS or GitHub Actions for signed .dmg" >&2
    else TARGETS=("linux" "win"); fi ;;
  *) TARGETS=("$TARGET") ;;
esac
echo "  targets: ${TARGETS[*]}"

step "Bundling standalone Python runtime + backend dependencies"
for t in "${TARGETS[@]}"; do
  case "$t" in
    win)   PY_TARGET="win" ;;
    mac)   if [ "$(uname -m)" = "arm64" ]; then PY_TARGET="mac-arm"; else PY_TARGET="mac-x64"; fi ;;
    linux) PY_TARGET="linux" ;;
    *)     PY_TARGET="$t" ;;
  esac
  bash "$DESKTOP/scripts/download-python.sh" "$PY_TARGET"
done

step "Building React frontend"
( cd "$FRONTEND" && yarn install --frozen-lockfile && REACT_APP_BACKEND_URL="$BACKEND_URL" yarn build )

step "Installing Electron + electron-builder"
( cd "$DESKTOP" && yarn install --frozen-lockfile )

for t in "${TARGETS[@]}"; do
  step "Packaging desktop binary for: $t"
  ( cd "$DESKTOP" && yarn "dist:$t" )
done

step "Build complete"
echo "Artifacts in: $DESKTOP/dist"
ls -lh "$DESKTOP/dist" 2>/dev/null | grep -E "\.(exe|dmg|AppImage|zip)$" || true
