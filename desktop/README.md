# Ledgerly Desktop (Electron)

This folder turns the Ledgerly web app into a standalone desktop application for **Windows** and **macOS**.

## Architecture
- The Electron main process (`main.js`) starts the **FastAPI backend** on `127.0.0.1:8001` as a child process.
- It then loads the built **React frontend** (from `../frontend/build`) inside an Electron window.
- All app data is stored in **MongoDB** running on the user's machine.

## Prerequisites (one-time, on each developer's machine)

| Tool      | Why                                  | Install |
|-----------|--------------------------------------|---------|
| Node.js 20+ | Electron + frontend build           | https://nodejs.org |
| Yarn      | Package manager                      | `npm i -g yarn` |
| Python 3.11+ | Runs FastAPI backend              | https://python.org |
| MongoDB Community 7+ | Persistent storage         | https://www.mongodb.com/try/download/community |

After installing MongoDB, make sure it is running locally on `mongodb://localhost:27017`.

Install Python deps **once**:
```bash
cd ../backend
pip install -r requirements.txt
```

## Build the desktop app

```bash
# from /desktop
yarn install                  # installs Electron + electron-builder
yarn build:frontend           # produces ../frontend/build with REACT_APP_BACKEND_URL=http://127.0.0.1:8001

# Build for the platform you are currently on:
yarn dist:win                 # Windows .exe (NSIS installer)  — must be run on Windows
yarn dist:mac                 # macOS .dmg                      — must be run on macOS
yarn dist:linux               # Linux AppImage
```

Output binaries land in `desktop/dist/`.

> **Note**: `electron-builder` cannot cross-compile signed `.exe` from macOS or signed `.dmg` from Windows.
> Use a real Windows machine for the Windows build and a real Mac for the Mac build, or use GitHub Actions
> (sample workflow below) to build all targets in CI.

## Develop locally (hot reload)

```bash
# Terminal 1 — start the backend
cd ../backend
python -m uvicorn server:app --reload --port 8001

# Terminal 2 — start the React dev server
cd ../frontend
REACT_APP_BACKEND_URL=http://127.0.0.1:8001 yarn start

# Terminal 3 — start Electron pointing at the dev server
cd ../desktop
yarn install
yarn start
```

## GitHub Actions (build all 3 platforms automatically)

Create `.github/workflows/desktop-build.yml` in your repo:

```yaml
name: Build desktop binaries
on:
  push:
    tags: ["v*"]
jobs:
  build:
    strategy:
      matrix:
        os: [windows-latest, macos-latest, ubuntu-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r backend/requirements.txt
      - run: cd frontend && yarn install && yarn build
        env:
          REACT_APP_BACKEND_URL: http://127.0.0.1:8001
      - run: cd desktop && yarn install && yarn dist:${{ runner.os == 'macOS' && 'mac' || runner.os == 'Windows' && 'win' || 'linux' }}
      - uses: actions/upload-artifact@v4
        with:
          name: ledgerly-${{ matrix.os }}
          path: desktop/dist/*.{exe,dmg,AppImage}
```

## Troubleshooting

- **Backend fails to start**: ensure `python3` is on PATH, or set the env var `LEDGERLY_PYTHON=/full/path/to/python` before launching.
- **MongoDB connection refused**: ensure `mongod` is running. Verify with `mongosh`.
- **Stale frontend build**: re-run `yarn build:frontend`.
