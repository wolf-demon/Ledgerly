# Ledgerly

A personal finance categorizer that ingests bank statements (CSV / PDF), groups transactions into income and expense categories, learns rules from your picks, and shows yearly / monthly / per-merchant breakdowns. Runs as a web app or as a native **Windows / macOS desktop app** via Electron.

```
ledgerly/
├── backend/        FastAPI + MongoDB API (port 8001)
├── frontend/       React 19 + Tailwind + Shadcn UI
└── desktop/        Electron wrapper for native Windows / macOS / Linux builds
```

## Run as a web app (development)

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
python -m uvicorn server:app --reload --port 8001
# Defaults to SQLite (writes ./ledgerly.db). Set STORAGE=mongo + MONGO_URL to use MongoDB instead.

# 2. Frontend
cd ../frontend
yarn install
yarn start          # opens http://localhost:3000
```

The frontend reads `REACT_APP_BACKEND_URL` from `frontend/.env`.

## Build a native Windows / macOS desktop app

The desktop build does **not** require MongoDB — it bundles a SQLite-backed FastAPI inside Electron.

```powershell
# Windows
cd desktop
.\build.ps1                    # builds for the current OS
.\build.ps1 -Targets all       # everything this machine can produce
```

```bash
# macOS / Linux
cd desktop
./build.sh                     # current OS
./build.sh all                 # everything this machine can produce
```

Binaries land in `desktop/dist/`. See `desktop/README.md` for the cross-compilation table and full details. To produce **signed** binaries for all three OSes from a single tag push, use the included GitHub Actions workflow at `.github/workflows/desktop-build.yml`.

## Features

- Multi-project workspaces (Personal, Business, etc.)
- CSV & PDF bank statement import with auto-dedupe
- AI-suggested category (Claude Sonnet 4.5)
- Rule learning — recurring merchants auto-categorize on future imports
- Yearly heatmap (category × month) with click-through to transactions
- Monthly cashflow & expense pie charts
- Recurring transaction detection + monthly forecast
- Bulk categorize, search, CSV export

## Stack

- **Backend**: FastAPI · Motor (MongoDB) · pandas · pdfplumber · emergentintegrations
- **Frontend**: React 19 · Tailwind · Shadcn UI · Recharts · Framer Motion
- **Desktop**: Electron 32 · electron-builder
