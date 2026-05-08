# Ledgerly — Personal Finance Categorizer

## Original Problem Statement
Web app to import monthly bank statements (CSV/PDF), categorize transactions, learn rules, and visualize yearly/monthly breakdowns. Multiple projects. GBP. Single-user. Plus native Windows/Mac builds via Electron.

## Architecture
- **Frontend**: React 19 + TailwindCSS + Shadcn UI + Recharts + Framer Motion
- **Backend**: FastAPI + Motor (MongoDB) + pandas + pdfplumber + emergentintegrations (Claude Sonnet 4.5)
- **Desktop**: Electron 32 + electron-builder (in `/desktop`)
- **DB collections**: projects, categories, transactions, rules

## Implemented
### Iteration 1 (2026-02-08)
- Multi-project switcher with default category seeding
- CSV & PDF upload with auto column detection and dedupe
- AI category suggestion (Claude Sonnet 4.5)
- Rule learning + back-apply
- Categories CRUD with color palette
- Transactions list with categorize dialog
- Dashboard: cashflow + pie + summary cards
- Yearly heatmap report with category drill-down

### Iteration 2 (2026-02-08)
- Uncategorized rows split into income/expense buckets in heatmap
- **Bulk categorize** (multi-select with optional "remember rule")
- **CSV export** of all transactions
- **Recurring transaction detector + monthly forecast** page
- **Electron desktop wrapper** (`/desktop/`) with Windows/macOS/Linux builders
- GitHub Actions workflow `.github/workflows/desktop-build.yml` for cross-platform CI builds
- README + desktop/README with full build instructions

## Test Credentials
N/A (no auth)

## Test Reports
- `/app/test_reports/iteration_1.json` — 15/15 backend, 100% frontend
- `/app/test_reports/iteration_2.json` — 11/11 new backend, 100% new frontend
- `/app/test_reports/iteration_3.json` — 26/26 regression on SQLite, 100% smoke

### Iteration 3 (2026-02-08) — SQLite swap
- **Storage swap: MongoDB → SQLite** (default; switchable via `STORAGE` env var)
- Thin Motor-compatible wrapper `/app/backend/sqlite_db.py` so `server.py` is unchanged
- Desktop Electron build needs **no MongoDB** — single-binary friendly
- Per-user SQLite DB stored under OS app-data dir
- New `desktop/build.ps1` (PowerShell) and `desktop/build.sh` (bash) one-command build scripts

## Backlog
- P1: Refactor server.py (~860 lines) into routers/ subpackage when convenient
- P1: Bank-specific PDF parser overrides (Lloyds, Monzo, Starling)
- P2: Budget targets per category with progress bars
- P2: PRAGMA integrity_check on startup with WAL-orphan warning
- P2: Auto-update channel for desktop binaries
