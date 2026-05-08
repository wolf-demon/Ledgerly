# Ledgerly Desktop (Electron)

Standalone desktop app for **Windows** and **macOS**. Stores everything in a local SQLite file and **bundles its own Python runtime** — end-users do not need MongoDB, Python, or anything else installed.

## Architecture
- Electron main process (`main.js`) starts the FastAPI backend on `127.0.0.1:8001` as a child process, using the **bundled Python runtime** under `<resources>/python/`.
- The packaged React build is loaded from `<resources>/frontend/index.html` (relative-asset paths via `homepage: "./"`, `HashRouter` for `file://` compatibility).
- All app data is stored in:
  - **Windows**: `%APPDATA%\Ledgerly\ledgerly.db`
  - **macOS**: `~/Library/Application Support/Ledgerly/ledgerly.db`
  - **Linux**: `~/.config/Ledgerly/ledgerly.db`
- A startup log is written to `<userData>/ledgerly.log` for troubleshooting.

## Prerequisites — for the *developer building the installer*

| Tool      | Why                          | Install |
|-----------|------------------------------|---------|
| Node.js 20+ | Electron + frontend build  | https://nodejs.org |
| Yarn      | Package manager              | `npm i -g yarn` |

That's it. Python is downloaded automatically by the build script (via [python-build-standalone](https://github.com/astral-sh/python-build-standalone)) and bundled inside the installer. **End users need nothing.**

## One-command build

### Windows (PowerShell)
```powershell
cd desktop
.\build.ps1                    # build for current OS
.\build.ps1 -Targets win       # explicit Windows .exe
.\build.ps1 -Targets all       # everything this machine can produce
```

### macOS / Linux (bash)
```bash
cd desktop
./build.sh                     # current OS
./build.sh mac                 # macOS .dmg
./build.sh all                 # everything this machine can produce
```

The script:
1. Checks Node + Yarn are installed.
2. Downloads `python-build-standalone` (CPython 3.12.10) for the target platform — cached under `desktop/.cache/`.
3. Pip-installs the backend's requirements.txt into the bundled runtime.
4. Builds the React frontend with `REACT_APP_BACKEND_URL=http://127.0.0.1:8001`.
5. Runs `electron-builder`, which ships:
   - the React `build/` → `<resources>/frontend/`
   - the FastAPI source → `<resources>/backend/`
   - the bundled CPython → `<resources>/python/`

Output lands in `desktop/dist/`.

> **Installer size**: expect ~150 MB compressed (Python runtime + pip deps add ~80 MB; the rest is Electron + React build). This is normal for a self-contained desktop Python+Electron app.

## Cross-compilation honest note

| Host    | Reliable binaries          | Won't reliably produce |
|---------|----------------------------|------------------------|
| Windows | `.exe` (signed/unsigned)   | Signed Mac `.dmg` (Apple needs macOS to codesign/notarize) |
| macOS   | `.dmg`, `.exe`, `.AppImage` | Signed Windows `.exe` codesigning needs Windows tooling |
| Linux   | `.AppImage`, `.exe`        | Mac `.dmg` |

For signed binaries on every platform from one tag push, use `.github/workflows/desktop-build.yml`.

## Troubleshooting

### "Blank white screen" after install
Almost always one of:
1. **Old build cached** — wipe `desktop/dist/` and re-run `.\build.ps1`.
2. **Frontend bundle missing** — log will say "Frontend bundle not found". Re-run `.\build.ps1` (don't pass `-SkipFrontend` on the first build).
3. **Bundled Python missing** — log will say "Could not start backend". Re-run `.\build.ps1` (do not delete `desktop/python-runtime` between runs).

### Open DevTools to inspect errors
```powershell
$env:LEDGERLY_DEBUG=1
& "$env:LOCALAPPDATA\Programs\ledgerly\Ledgerly.exe"
```
On macOS:
```bash
LEDGERLY_DEBUG=1 open -a Ledgerly
```

### Reset all data
Quit Ledgerly, then delete `%APPDATA%\Ledgerly\ledgerly.db` (Windows) or `~/Library/Application Support/Ledgerly/ledgerly.db` (macOS). Next launch creates a fresh DB.

### Force a re-download of the bundled Python
```powershell
.\scripts\download-python.ps1 -Target win -Force
```
or simply delete `desktop/.cache/` and `desktop/python-runtime/` and rebuild.

## Auto-update channel

Ledgerly ships with [`electron-updater`](https://www.electron.build/auto-update). Once an
installed copy is launched, it:

1. Waits ~4 seconds for the local backend + UI to come up.
2. Hits the publish target configured at build time and compares versions.
3. Downloads the new installer **in the background**, then asks the user to
   restart now or apply on next quit.
4. Repeats the check every 6 hours while the app is running.
5. **Help → Check for Updates…** menu also runs the check on demand.

Differential updates (NSIS `differentialPackage`) are enabled, so users only
download the changed bytes between versions.

### Default publish target — GitHub Releases

Set two env vars before running the publish script and `electron-builder` will
upload the artifacts (`*.exe`, `*.dmg`, `*.zip`, `*.AppImage`) plus the
`latest*.yml` manifests to a draft release for the matching tag:

```bash
export LEDGERLY_GH_OWNER=your-github-username-or-org
export LEDGERLY_GH_REPO=ledgerly
export GH_TOKEN=ghp_xxx_with_repo_scope     # personal access token
cd desktop
yarn publish:win        # or publish:mac / publish:linux / publish:all
```

`GH_TOKEN` is what `electron-builder` uses to upload. Promote the draft to a
published release and every installed Ledgerly will pick it up on its next
update check.

### Custom feed (S3, your own server, etc.)

Override the feed at runtime — the installed app will pull `latest*.yml`
from this URL instead of GitHub:

```bash
LEDGERLY_UPDATE_FEED=https://updates.example.com/ledgerly/  Ledgerly.exe
```

For a permanent custom target, change the `build.publish` block in
`desktop/package.json` (e.g. `provider: "s3"` or `"generic"`). See
https://www.electron.build/configuration/publish for all providers.

### Pre-release channels

Ship beta builds by tagging a pre-release version (`1.2.0-beta.1`) **and**
launching with the matching channel env var so the updater knows it should
look at pre-releases:

```bash
LEDGERLY_UPDATE_CHANNEL=beta   Ledgerly.exe
```

### Code-signing & notarization

Auto-update *works* with unsigned builds (Windows + Linux), but macOS will
refuse to install an unsigned `.dmg` silently — users need to dismiss
Gatekeeper warnings each time. For a smooth UX:
- **Windows**: provide an EV/OV codesign certificate via `CSC_LINK` +
  `CSC_KEY_PASSWORD` env vars.
- **macOS**: configure `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, `CSC_LINK`,
  `CSC_KEY_PASSWORD` so `electron-builder` notarizes the `.dmg` and `.zip`.
  The `.zip` is what `electron-updater` actually installs from on macOS.

## Develop locally (hot reload)

```bash
# Terminal 1 — backend (uses your system python in dev)
cd backend && python -m uvicorn server:app --reload --port 8001

# Terminal 2 — React dev server
cd frontend && REACT_APP_BACKEND_URL=http://127.0.0.1:8001 yarn start

# Terminal 3 — Electron pointing at the dev server
cd desktop && yarn install && yarn start
```

In dev mode `LEDGERLY_DEBUG` is automatically true, so DevTools opens on launch.
