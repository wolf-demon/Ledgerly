# build.ps1 — Builds Ledgerly desktop app on Windows.
#
# Usage (from PowerShell or PowerShell Core):
#   .\build.ps1                 # build for current OS only
#   .\build.ps1 -Targets win    # build Windows .exe installer
#   .\build.ps1 -Targets mac    # attempts Mac .dmg (UNSIGNED — see notes below)
#   .\build.ps1 -Targets all    # attempts every target this machine can produce
#
# Honest note on cross-compilation:
# - Windows -> Windows: works perfectly (signed/unsigned NSIS .exe).
# - Windows -> Mac: electron-builder can produce an UNSIGNED .dmg from Windows,
#   but it cannot codesign/notarize it (Apple requires macOS for that). The
#   resulting .dmg will warn users on first launch ("unidentified developer").
#   For a real signed Mac build, run this script on a Mac, or use the GitHub
#   Actions workflow at .github/workflows/desktop-build.yml.
# - Mac -> Windows / Linux: also works via this same script under PowerShell Core.

[CmdletBinding()]
param(
    [ValidateSet("win", "mac", "linux", "all", "current")]
    [string]$Targets = "current",

    [switch]$SkipFrontend,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Resolve-Path (Join-Path $ScriptDir "..")
$Frontend  = Join-Path $RepoRoot "frontend"
$Desktop   = $ScriptDir
$BackendUrl = "http://127.0.0.1:8001"

function Write-Step($msg) {
    Write-Host "`n==> $msg" -ForegroundColor Cyan
}
function Assert-Cmd($name, $hint) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: '$name' not found on PATH. $hint" -ForegroundColor Red
        exit 1
    }
}

# 1. Pre-flight checks ---------------------------------------------------
Write-Step "Pre-flight checks"
Assert-Cmd "node"   "Install Node.js 20+ from https://nodejs.org"
Assert-Cmd "yarn"   "Run: npm install -g yarn"
Assert-Cmd "python" "Install Python 3.11+ from https://python.org (must be on PATH)"

$nodeVer   = (& node --version).Trim()
$pythonVer = (& python --version 2>&1).ToString().Trim()
Write-Host "  node   : $nodeVer"
Write-Host "  yarn   : $(& yarn --version)"
Write-Host "  python : $pythonVer"

# 2. Resolve targets -----------------------------------------------------
$os = if ($IsWindows -or $env:OS -eq "Windows_NT") { "win" }
      elseif ($IsMacOS) { "mac" }
      elseif ($IsLinux) { "linux" }
      else { "win" }

$targetList = @()
switch ($Targets) {
    "current" { $targetList = @($os) }
    "all"     {
        if ($os -eq "mac") { $targetList = @("mac", "win", "linux") }
        elseif ($os -eq "win") { $targetList = @("win", "linux") ; Write-Host "WARNING: Mac build skipped (cannot sign .dmg from Windows). Use GitHub Actions for signed Mac builds." -ForegroundColor Yellow }
        else { $targetList = @("linux", "win") }
    }
    default { $targetList = @($Targets) }
}
Write-Host "  targets: $($targetList -join ', ')"

# 3. Install Python deps -------------------------------------------------
Write-Step "Installing Python backend dependencies"
Push-Location (Join-Path $RepoRoot "backend")
& python -m pip install --quiet -r requirements.txt
Pop-Location

# 4. Build the React frontend -------------------------------------------
if (-not $SkipFrontend) {
    Write-Step "Building React frontend (REACT_APP_BACKEND_URL=$BackendUrl)"
    Push-Location $Frontend
    & yarn install --frozen-lockfile
    $env:REACT_APP_BACKEND_URL = $BackendUrl
    & yarn build
    Pop-Location
}

# 5. Install Electron deps ----------------------------------------------
Write-Step "Installing Electron + electron-builder"
Push-Location $Desktop
& yarn install --frozen-lockfile

# 6. Build per-target ----------------------------------------------------
foreach ($t in $targetList) {
    Write-Step "Packaging desktop binary for: $t"
    & yarn ("dist:$t")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FAILED: dist:$t" -ForegroundColor Red
        Pop-Location
        exit 1
    }
}
Pop-Location

# 7. Done ----------------------------------------------------------------
$dist = Join-Path $Desktop "dist"
Write-Step "Build complete"
Write-Host "Artifacts in: $dist" -ForegroundColor Green
if (Test-Path $dist) {
    Get-ChildItem $dist | Where-Object { $_.Extension -in ".exe", ".dmg", ".AppImage", ".zip" } | ForEach-Object {
        $sizeMB = [math]::Round($_.Length / 1MB, 1)
        Write-Host ("  - {0}  ({1} MB)" -f $_.Name, $sizeMB)
    }
}
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  Windows : double-click the .exe under $dist to install Ledgerly"
Write-Host "  macOS   : open the .dmg, drag Ledgerly to Applications"
Write-Host "  Linux   : chmod +x the .AppImage, then run it"
