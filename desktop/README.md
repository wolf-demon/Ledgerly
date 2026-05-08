# Ledgerly Desktop (Electron)

Standalone desktop app for **Windows** and **macOS**. Stores everything in a local SQLite file — no MongoDB or other server required.

## Architecture
- Electron main process (`main.js`) starts the FastAPI backend on `127.0.0.1:8001` as a child process and points it at a per-user SQLite file.
- The packaged React build is loaded from `<resources>/frontend/index.html` (relative-asset paths via `homepage: "./"`, `HashRouter` for `file://` compatibility).
- All app data is stored in:
  - **Windows**: `%APPDATA%\Ledgerly\ledgerly.db`
  - **macOS**: `~/Library/Application Support/Ledgerly/ledgerly.db`
  - **Linux**: `~/.config/Ledgerly/ledgerly.db`
- A startup log is written to `<userData>/ledgerly.log` for troubleshooting.

## Prerequisites (one-time)

| Tool      | Why                                  | Install |
|-----------|--------------------------------------|---------|
| Node.js 20+ | Electron + frontend build           | https://nodejs.org |
| Yarn      | Package manager                      | `npm i -g yarn` |
| Python 3.11+ | Runs FastAPI backend              | https://python.org **(tick "Add Python to PATH" in the installer)** |

That's it — no MongoDB.

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

The script: pre-flight checks → pip install backend → React build (with `REACT_APP_BACKEND_URL=http://127.0.0.1:8001`) → `yarn install` in desktop/ → `electron-builder`. Output lands in `desktop/dist/`.

## Cross-compilation honest note

| Host    | Reliable binaries          | Won't reliably produce |
|---------|----------------------------|------------------------|
| Windows | `.exe` (signed/unsigned)   | Signed Mac `.dmg` (Apple needs macOS to codesign/notarize) |
| macOS   | `.dmg`, `.exe`, `.AppImage` | Signed Windows `.exe` codesigning needs Windows tooling |
| Linux   | `.AppImage`, `.exe`        | Mac `.dmg` |

For signed binaries on every platform, push a tag and let `.github/workflows/desktop-build.yml` build all three.

## Troubleshooting

### "Blank white screen" after install
Almost always one of:
1. **Old build cached** — wipe `desktop/dist/` and re-run `.\build.ps1`.
2. **Python not on PATH** — open `%APPDATA%\Ledgerly\ledgerly.log` (or `~/Library/Application Support/Ledgerly/ledgerly.log` on macOS) and look for "FATAL: failed to spawn python". Re-install Python with the **"Add Python to PATH"** checkbox ticked.
3. **Frontend bundle missing** — the log will say "Frontend bundle not found". Re-run `.\build.ps1` (don't pass `-SkipFrontend` on the first build).

### Open DevTools to inspect errors
```powershell
$env:LEDGERLY_DEBUG=1
& "C:\Users\you\AppData\Local\Programs\ledgerly\Ledgerly.exe"
```
DevTools opens in a side panel; check the **Console** and **Network** tabs.

### Backend dependencies fail to install
Run manually:
```bash
cd backend
python -m pip install -r requirements.txt
```

### Reset all data
Quit Ledgerly, then delete `%APPDATA%\Ledgerly\ledgerly.db` (Windows) or the equivalent on macOS / Linux. Next launch creates a fresh DB.

## Develop locally (hot reload)

```bash
# Terminal 1 — backend
cd backend && python -m uvicorn server:app --reload --port 8001

# Terminal 2 — React dev server
cd frontend && REACT_APP_BACKEND_URL=http://127.0.0.1:8001 yarn start

# Terminal 3 — Electron pointing at the dev server
cd desktop && yarn install && yarn start
```

In dev mode `LEDGERLY_DEBUG` is automatically true, so DevTools opens on launch.
