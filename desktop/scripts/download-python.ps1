# download-python.ps1 — downloads python-build-standalone for the chosen target,
# extracts it under desktop\python-runtime, and pip-installs the backend requirements.
# Called automatically by build.ps1.

[CmdletBinding()]
param(
    [ValidateSet("win", "mac-arm", "mac-x64", "linux")]
    [string]$Target = "win",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir = Resolve-Path (Join-Path $ScriptDir "..")
$RepoRoot = Resolve-Path (Join-Path $DesktopDir "..")
$BackendReqs = Join-Path $RepoRoot "backend\requirements-desktop.txt"
$RuntimeDir = Join-Path $DesktopDir "python-runtime"
$CacheDir = Join-Path $DesktopDir ".cache"
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null

# Pinned, known-good release of python-build-standalone (Python 3.12).
$PB_RELEASE = "20260504"
$PY_VERSION = "3.12.13"

$assets = @{
    "win"     = "cpython-${PY_VERSION}+${PB_RELEASE}-x86_64-pc-windows-msvc-install_only.tar.gz"
    "mac-arm" = "cpython-${PY_VERSION}+${PB_RELEASE}-aarch64-apple-darwin-install_only.tar.gz"
    "mac-x64" = "cpython-${PY_VERSION}+${PB_RELEASE}-x86_64-apple-darwin-install_only.tar.gz"
    "linux"   = "cpython-${PY_VERSION}+${PB_RELEASE}-x86_64-unknown-linux-gnu-install_only.tar.gz"
}

$asset = $assets[$Target]
$url = "https://github.com/astral-sh/python-build-standalone/releases/download/${PB_RELEASE}/${asset}"
$tarball = Join-Path $CacheDir $asset

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

Step "Target: $Target  |  python-build-standalone $PB_RELEASE  |  CPython $PY_VERSION"

# 1. Download (with cache)
if ($Force -or -not (Test-Path $tarball)) {
    Step "Downloading $asset"
    Write-Host "  $url"
    Invoke-WebRequest -Uri $url -OutFile $tarball -UseBasicParsing
} else {
    Write-Host "  using cached $tarball" -ForegroundColor DarkGray
}

# 2. Clean target dir & extract
if (Test-Path $RuntimeDir) {
    Step "Cleaning previous python-runtime"
    Remove-Item -Recurse -Force $RuntimeDir
}
New-Item -ItemType Directory -Path $RuntimeDir | Out-Null

Step "Extracting Python runtime"
# tar comes with Windows 10+ by default
& tar -xzf $tarball -C $RuntimeDir
if ($LASTEXITCODE -ne 0) { throw "tar extract failed" }

# python-build-standalone tarballs put everything under a top-level "python/" dir.
# Flatten so $RuntimeDir/python.exe (Windows) or $RuntimeDir/bin/python3 (Unix).
$Inner = Join-Path $RuntimeDir "python"
if (Test-Path $Inner) {
    Get-ChildItem $Inner | Move-Item -Destination $RuntimeDir
    Remove-Item $Inner
}

# 3. Locate the python executable
if ($Target -eq "win") {
    $PYTHON = Join-Path $RuntimeDir "python.exe"
} else {
    $PYTHON = Join-Path $RuntimeDir "bin\python3"
}

if (-not (Test-Path $PYTHON)) {
    throw "Bundled python not found at expected path: $PYTHON"
}

# 4. Install backend requirements into the bundled runtime
Step "Installing backend requirements into bundled Python"
& $PYTHON -m pip install --upgrade pip --no-warn-script-location | Out-Host
& $PYTHON -m pip install --no-warn-script-location -r $BackendReqs | Out-Host
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# 5. Trim obvious dead weight (caches, tests inside site-packages, .pyc)
Step "Trimming runtime"
$siteRoot = if ($Target -eq "win") { Join-Path $RuntimeDir "Lib\site-packages" } else { Join-Path $RuntimeDir "lib\python3.12\site-packages" }
Get-ChildItem -Path $RuntimeDir -Include __pycache__, tests, test -Recurse -Directory -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path $RuntimeDir -Include *.pyc, *.pyi -Recurse -File -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue
$strip = @("pip", "setuptools", "wheel", "_distutils_hack",
           "googleapiclient", "stripe", "boto3", "botocore", "s3transfer",
           "oauthlib", "requests_oauthlib")
foreach ($pkg in $strip) {
    Get-ChildItem -Path $siteRoot -Filter "$pkg*" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

$Size = (Get-ChildItem -Recurse $RuntimeDir | Measure-Object -Property Length -Sum).Sum
Write-Host ("`n==> Bundled python ready at $RuntimeDir  ({0:N1} MB)" -f ($Size / 1MB)) -ForegroundColor Green
