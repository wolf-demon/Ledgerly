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
