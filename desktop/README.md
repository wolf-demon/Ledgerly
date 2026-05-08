# Ledgerly Desktop (Electron)

This folder turns the Ledgerly web app into a standalone desktop application for **Windows** and **macOS** — **no database server required**. Data is stored in a single local SQLite file (`ledgerly.db`) inside the user's app-data directory.

## Architecture
- The Electron main process (`main.js`) starts the **FastAPI backend** on `127.0.0.1:8001` as a child process.
- It then loads the built **React frontend** (from `../frontend/build`) inside an Electron window.
- All app data is stored in a **local SQLite file**. No MongoDB, no external services.

## Prerequisites (one-time, on each developer's machine)

| Tool      | Why                                  | Install |
|-----------|--------------------------------------|---------|
| Node.js 20+ | Electron + frontend build           | https://nodejs.org |
| Yarn      | Package manager                      | `npm i -g yarn` |
| Python 3.11+ | Runs FastAPI backend              | https://python.org (must be on PATH) |

That's it — **MongoDB is no longer required**.

## One-command build

### From Windows (PowerShell)
```powershell
cd desktop
.\build.ps1                    # builds for current OS
.\build.ps1 -Targets win       # explicit Windows .exe installer
.\build.ps1 -Targets all       # everything this machine can produce
```

### From macOS / Linux (bash)
```bash
cd desktop
./build.sh                     # current OS
./build.sh mac                 # macOS .dmg
./build.sh all                 # everything this machine can produce
```

The script:
1. Checks Node, Yarn, Python are installed.
2. `pip install`s the backend's Python deps.
3. Builds the React frontend with `REACT_APP_BACKEND_URL=http://127.0.0.1:8001`.
4. Runs `yarn install` in `desktop/` and runs the matching `electron-builder` target.
5. Drops finished installers into `desktop/dist/`.

## Cross-compilation honest disclaimer

| Host    | Can build               | Cannot build (reliably)                    |
|---------|-------------------------|--------------------------------------------|
| Windows | `.exe` (signed/unsigned) | Signed Mac `.dmg` (Apple requires macOS for codesign/notarize) |
| macOS   | `.dmg`, `.exe`, `.AppImage` | Signed Windows `.exe` requires Windows codesign tooling |
| Linux   | `.exe`, `.AppImage`     | Mac `.dmg` (no Apple toolchain on Linux)   |

For **signed binaries on every platform**, push a tag to your GitHub repo and the included
`.github/workflows/desktop-build.yml` will produce all three on dedicated runners (Windows, macOS, Ubuntu).

## Develop locally (hot reload)

```bash
# Terminal 1 — backend
cd backend && python -m uvicorn server:app --reload --port 8001

# Terminal 2 — React dev server
cd frontend && REACT_APP_BACKEND_URL=http://127.0.0.1:8001 yarn start

# Terminal 3 — Electron window pointing at the dev server
cd desktop && yarn install && yarn start
```

## Data location

After install:
- **Windows**: `%APPDATA%\Ledgerly\ledgerly.db`
- **macOS**: `~/Library/Application Support/Ledgerly/ledgerly.db`
- **Linux**: `~/.config/Ledgerly/ledgerly.db`

The path is set via the `SQLITE_PATH` env var that Electron passes to the backend; defaults to a file alongside `server.py` in dev mode.

## Troubleshooting

- **Backend fails to start**: ensure `python` is on PATH, or set `LEDGERLY_PYTHON=/full/path/to/python` before launching the app.
- **"AssertionError: SQLITE_PATH"**: delete `ledgerly.db` and restart — it will be recreated.
- **Stale frontend build**: re-run `yarn build:frontend`.
