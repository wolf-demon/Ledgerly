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

### Iteration 7 (2026-02-08) — Sign-flip fix, batch AI, Emergent key UI
- **Critical bug fix**: when a category is assigned (PUT /transactions/{id}, bulk-categorize, or apply_to_similar back-apply), the transaction's amount sign is now forced to match the category's type. Fixes "everything shows as income on dashboard even after categorizing as expense" caused by parser-imported all-positive amounts.
- **`POST /api/transactions/reclassify`** enhanced: for categorized tx → sign + type from category; for uncategorized → type from amount sign.
- **`POST /api/transactions/bulk-suggest`** — new endpoint runs the configured AI provider over many uncategorized transactions in one go. Groups by normalized merchant key (one AI call per unique merchant), persists CategoryRule per key. `allow_create=true` lets the AI invent new sensibly-named categories on the fly. Sign-flips applied automatically.
- **Frontend**: "Auto-categorize with AI" button on the Transactions page (top-right, alongside Re-classify and Export CSV).
- **Emergent key UI**: Settings page adds a card with a masked password input + show/hide eye toggle + Test connection button. `AppSettings.emergent_key` falls back to bundled env key.
- **`POST /api/settings/test-emergent`** — verifies any pasted key by issuing a tiny "ping" request.
- Tests: 13/13 new + 54 regression = **67/68 passing** (1 skip: .xls writer not in env).

### Iteration 6 (2026-02-08) — Parser sign fix + Settings page + Ollama
- **Parser fix**: Debit/Credit columns now take precedence over a duplicate unsigned Amount column; new Type column hint (DR/CR/DEBIT/CREDIT/IN/OUT) applied to unsigned Amount values. Fixes "all transactions tagged as income" bug for UK bank CSV exports.
- **POST /api/transactions/reclassify** — re-derives `type` from `amount` sign for an entire project (one-click repair for already-imported wrong data).
- **Settings page** at `/settings`: AI provider selector (Emergent cloud / Ollama local / Disabled), Ollama URL + model fields, "Test connection" button, OS-aware install instructions with copy-to-clipboard buttons.
- **Ollama integration**: `/api/categorize/suggest` now dispatches via `settings.ai_provider`. Calls Ollama's `/api/chat` REST endpoint with `format: json` for structured output. Friendly error if Ollama isn't running or the model isn't pulled.
- **GET/PUT /api/settings**, **POST /api/settings/test-ollama** — new endpoints; `settings` table added to SQLite schema (auto-migrates on next startup).
- Sidebar nav: new "Settings" link.
- Tests: 12/12 new + 42 regression = **54/54 passing**.

### Iteration 5 (2026-02-08) — More file formats
- **Excel** (`.xlsx` via openpyxl, `.xls` via xlrd) — first sheet with Date/Description/Amount cols is auto-detected
- **OpenDocument Spreadsheet** (`.ods`) — LibreOffice / Apple Numbers exports
- **TSV** (tab-separated)
- **OFX / QFX** (Open Financial Exchange — most banks export this)
- **Google Sheets via public share URL** — backend transforms any `/spreadsheets/d/{ID}/edit...` URL into the CSV export URL, fetches and ingests; helpful "Anyone with the link" hint when the sheet is private
- **Generic public CSV/Excel URL** — same endpoint accepts any reachable file URL
- New `POST /api/transactions/import-url` endpoint, `parse_any` dispatcher, `google_sheet_to_csv_url` helper
- Upload page now has tabs: "Upload file" + "Google Sheets / URL" with paste-box + step-by-step help
- Tests: **16/16 new + 26/26 regression = 42/42 passing**

### Iteration 4 (2026-02-08) — Bundled Python runtime
- Desktop installer now bundles a complete CPython 3.12.13 runtime via [python-build-standalone](https://github.com/astral-sh/python-build-standalone)
- New `desktop/scripts/download-python.{ps1,sh}` — downloads target-platform tarball, pip-installs `requirements-desktop.txt` into it, trims dev tools / unused SDKs
- Slim `backend/requirements-desktop.txt` (12 packages vs 60+) keeps the runtime to ~500 MB
- `desktop/main.js` resolves Python from: `LEDGERLY_PYTHON` env > bundled at `<resources>/python/` > system fallback
- Build scripts no longer require Python on the developer's machine — only Node + Yarn
- End users need **nothing pre-installed** — Ledgerly is a true single-click install

### Iteration 3.1 (2026-02-08) — Electron blank-screen fixes
- Added `homepage: "./"` to frontend/package.json (relative asset paths under `file://`)
- App.js auto-uses `HashRouter` under `file://` protocol
- `desktop/package.json` ships frontend/backend via `extraResources` (cleaner than `files` paths)
- `desktop/main.js` writes `<userData>/ledgerly.log`, opens DevTools when `LEDGERLY_DEBUG=1`, shows OS dialog on fatal errors

## Backlog
- P1: Refactor server.py (~860 lines) into routers/ subpackage when convenient
- P1: Bank-specific PDF parser overrides (Lloyds, Monzo, Starling)
- P2: Budget targets per category with progress bars
- P2: PRAGMA integrity_check on startup with WAL-orphan warning
- P2: Auto-update channel for desktop binaries
