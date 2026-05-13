#!/usr/bin/env bash
# download-python.sh â€” bash equivalent of download-python.ps1 for macOS / Linux.
# Downloads python-build-standalone for the chosen target, extracts under
# desktop/python-runtime, and pip-installs the backend requirements.
# Uses LF line endings for Unix runners.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_DIR/.." && pwd)"
BACKEND_REQS="$REPO_ROOT/backend/requirements-desktop.txt"
RUNTIME_DIR="$DESKTOP_DIR/python-runtime"
CACHE_DIR="$DESKTOP_DIR/.cache"
mkdir -p "$CACHE_DIR"

PB_RELEASE="20260504"
PY_VERSION="3.12.13"

TARGET="${1:-current}"
if [ "$TARGET" = "current" ]; then
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm64)  TARGET="mac-arm" ;;
        Darwin-x86_64) TARGET="mac-x64" ;;
        Linux-aarch64) TARGET="linux-arm64" ;;
        Linux-x86_64)  TARGET="linux" ;;
        MINGW*|MSYS*|CYGWIN*) TARGET="win" ;;
        *) TARGET="linux" ;;
    esac
fi

case "$TARGET" in
    win)         ASSET="cpython-${PY_VERSION}+${PB_RELEASE}-x86_64-pc-windows-msvc-install_only.tar.gz" ;;
    mac-arm)     ASSET="cpython-${PY_VERSION}+${PB_RELEASE}-aarch64-apple-darwin-install_only.tar.gz" ;;
    mac-x64)     ASSET="cpython-${PY_VERSION}+${PB_RELEASE}-x86_64-apple-darwin-install_only.tar.gz" ;;
    linux)       ASSET="cpython-${PY_VERSION}+${PB_RELEASE}-x86_64-unknown-linux-gnu-install_only.tar.gz" ;;
    linux-arm64) ASSET="cpython-${PY_VERSION}+${PB_RELEASE}-aarch64-unknown-linux-gnu-install_only.tar.gz" ;;
    *) echo "Unknown target: $TARGET" >&2; exit 1 ;;
esac

URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PB_RELEASE}/${ASSET}"
TARBALL="$CACHE_DIR/$ASSET"

step() { printf "\n\033[36m==> %s\033[0m\n" "$*"; }
step "Target: $TARGET  |  python-build-standalone $PB_RELEASE  |  CPython $PY_VERSION"

if [ ! -f "$TARBALL" ]; then
    step "Downloading $ASSET"
    echo "  $URL"
    if command -v curl >/dev/null 2>&1; then
        curl -L --fail -o "$TARBALL" "$URL"
    else
        wget -O "$TARBALL" "$URL"
    fi
else
    echo "  using cached $TARBALL"
fi

step "Cleaning previous python-runtime"
rm -rf "$RUNTIME_DIR"
mkdir -p "$RUNTIME_DIR"

step "Extracting Python runtime"
tar -xzf "$TARBALL" -C "$RUNTIME_DIR"

# Flatten the inner "python/" directory
if [ -d "$RUNTIME_DIR/python" ]; then
    mv "$RUNTIME_DIR/python/"* "$RUNTIME_DIR/" 2>/dev/null || true
    mv "$RUNTIME_DIR/python/".[!.]* "$RUNTIME_DIR/" 2>/dev/null || true
    rmdir "$RUNTIME_DIR/python"
fi

if [ "$TARGET" = "win" ]; then
    PYTHON="$RUNTIME_DIR/python.exe"
else
    PYTHON="$RUNTIME_DIR/bin/python3"
fi

if [ ! -f "$PYTHON" ]; then
    echo "Bundled python not found at $PYTHON" >&2
    exit 1
fi
chmod +x "$PYTHON" 2>/dev/null || true

step "Installing backend requirements into bundled Python"
EXTRA_INDEX="https://d33sy5i8bnduwe.cloudfront.net/simple/"
"$PYTHON" -m pip install --upgrade pip --no-warn-script-location
"$PYTHON" -m pip install --no-warn-script-location --extra-index-url "$EXTRA_INDEX" -r "$BACKEND_REQS"

step "Trimming runtime"
# Standard wheel trimming: pycache, tests, type stubs, build tooling we no longer need.
find "$RUNTIME_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$RUNTIME_DIR" -name "tests" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$RUNTIME_DIR" -name "test" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$RUNTIME_DIR" -type f \( -name "*.pyc" -o -name "*.pyi" -o -name "*.pyd.dist-info" \) -delete 2>/dev/null || true
# Drop pip/setuptools/wheel â€” runtime doesn't need to install more packages.
rm -rf "$RUNTIME_DIR"/lib/python*/site-packages/{pip,pip-*,setuptools,setuptools-*,wheel,wheel-*,_distutils_hack} 2>/dev/null || true
# Drop unused heavy SDKs that emergentintegrations pulled in transitively but Ledgerly never imports.
# (Keep cryptography - pdfminer needs it; keep bcrypt/passlib/jose/jwt - low cost, may be transitively needed)
rm -rf "$RUNTIME_DIR"/lib/python*/site-packages/{googleapiclient,stripe,boto3,botocore,s3transfer,oauthlib,requests_oauthlib} 2>/dev/null || true

SIZE=$(du -sh "$RUNTIME_DIR" | cut -f1)
printf "\n\033[32m==> Bundled python ready at %s  (%s)\033[0m\n" "$RUNTIME_DIR" "$SIZE"

