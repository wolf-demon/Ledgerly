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

### Iteration 8 (2026-02-08) — Backend modular refactor + desktop auto-update
- **server.py refactor**: 1410 lines → 65 lines. Split into:
  - `app_db.py` — storage backend selection + lifecycle hooks
  - `models.py` — all Pydantic models in one place
  - `services/helpers.py` — `normalize_merchant`, `parse_amount`, `parse_date`, `find_column`, `apply_rules`, **new `force_amount_sign(amount, cat_type)` helper** (replaces 5 copies of the sign-flipping logic across update_transaction, bulk_categorize, bulk_suggest, reclassify, apply_to_similar)
  - `services/parsers.py` — CSV/TSV/PDF/Excel/ODS/OFX + Google Sheets URL helpers
  - `services/ai.py` — Emergent + Ollama LLM calls
  - `services/settings_store.py` — get/save settings
  - `routes/{projects,categories,transactions,settings,analytics,categorize}.py` — one APIRouter per domain
  - `server.py` — app + middleware + router includes only
- Backward-compat re-exports in `server.py` (so existing test imports `from server import parse_csv` still work).
- Result: **67/68 tests passing** (same as before refactor — zero regressions; 1 skip is xlrd missing).

- **Auto-update channel for desktop binaries** via `electron-updater@6.x`:
  - New `desktop/updater.js` — wires startup check (4s after launch), 6-hourly checks, dialog on update available, restart/later prompt on download.
  - **Help → Check for Updates…** menu entry on Win/Linux/macOS.
  - `desktop/package.json` adds `publish:{win,mac,linux,all}` scripts and a GitHub Releases publish target controlled by `LEDGERLY_GH_OWNER` + `LEDGERLY_GH_REPO` env vars at publish time.
  - NSIS `differentialPackage: true` so users only download the changed bytes between versions.
  - Mac targets `dmg` + `zip` (zip is what electron-updater installs from on macOS).
  - Runtime overrides: `LEDGERLY_UPDATE_FEED` (custom feed URL) and `LEDGERLY_UPDATE_CHANNEL` (beta/alpha channels).
  - `desktop/README.md` — full new section covering GitHub Releases publishing, custom feeds, pre-release channels, code-signing requirements.

### Iteration 9 (2026-02-08) — Budget tracker

**Backend:**
- New `budgets` table in SQLite (`id, project_id, category_id, period, amount, rollover, created_at`).
- New `Budget` + `BudgetUpsert` models.
- New `routes/budgets.py`: GET/POST/DELETE `/api/budgets`, `GET /api/budgets/progress?project_id=X&year=Y&month=M`.
- POST upserts by (project, category, period); `amount=0` deletes.
- **Rollover** (monthly only): walks back ≤11 prior consecutive rollover months and accumulates `max(0, base − prior_spent)` into `effective_amount`.
- **Cascade delete**: `delete_project` and `delete_category` cascade into budgets.
- Income categories supported symmetrically as targets.

**Frontend:**
- New `/budgets` page (sidebar between Categories and Yearly Report), per-category amount + period (monthly/yearly) + rollover switch + live progress bar.
- Status colors: green ok / tan warn (≥80%) / red over (≥100%); over-budget banner at the top.
- New `BudgetSummary` Dashboard widget: empty CTA when no budgets, top-5 progress bars + "X on track · Y over" otherwise.

**Tests:**
- New `/app/backend/tests/test_iteration8_budgets.py` — 14 cases.
- Result: **14/14 new + 81/82 regression = 95/96 passing**, frontend e2e 12/12.

## Backlog
- P2: PRAGMA integrity_check on startup with WAL-orphan warning
- P2: In-app "Updates" banner driven by IPC bridge from `updater.js`
- P2: Sync Dashboard BudgetSummary period with `/budgets` page selector (cosmetic)
- P3: Document the minimum Electron version that supports CSS `color-mix()` (Chromium 111+) or ship a PostCSS fallback for the theme tints.
- P3: Wire `Skeleton`/`EmptyState` into more pages (Transactions list, Categories empty, Budgets empty) for fuller loading polish.

### Iteration 15 (2026-02-13) — Bug-fixes: flash on empty pages, tx-not-showing, GitHub Actions

**Reported by user:**
1. "Loading transactions" ↔ "No transactions yet" flashing on Transactions + Recurring pages when project is empty.
2. After iteration 14, freshly-added transactions don't show on the Transactions page.
3. GitHub Actions desktop release failed on macOS and Ubuntu (Windows succeeded).

**Root causes:**
1+2. `useFetchGuard()` was returning a **fresh function on every render** (not memoised), which broke every `useCallback([..., guard])` in every page. That cascaded into the consuming `useEffect([load, revision])` re-firing every render → infinite fetch loop → flash + the final state setter often raced and never landed → the new transactions never appeared.
   The aggressive `window.focus` listener I added in iteration 14 also fired far more often than expected in dev/Electron environments and exacerbated the loop.
3. `desktop/package.json` referenced `build-resources/icon.ico` and `icon.icns` but the `build-resources/` folder didn't even exist in the repo — electron-builder fails on Mac and (with strict icon paths) on Linux AppImage. Compounded by a `if: env.APPLE_CERT_P12 != ''` expression in the workflow that evaluated before env was assigned, so the Mac code-signing step ran unconditionally and tried to import a non-existent cert.

**Fixes:**
- **`lib/useFetchGuard.js`**: returned function is now wrapped in `useCallback([], [])` so it's referentially stable across renders. Pages that depend on `guard` in `useCallback` deps no longer re-fire.
- **`lib/projectContext.jsx`**: removed the `window.focus` auto-refresh. Mutations already call `bumpRevision()` — the focus listener was redundant and noisy.
- **`desktop/build-resources/icon.png`** (new): 1024×1024 brand PNG generated programmatically (sage-green rounded square + cream "L" mark + tan ledger underline). electron-builder auto-converts to `.icns` on Mac and `.ico` on Windows at build time.
- **`desktop/package.json`**: icon paths now uniformly point to the PNG; mac block adds `"identity": null` so unsigned local builds never block on keychain lookups.
- **`.github/workflows/desktop-release.yml`**:
  - Added `Install libfuse2` step for Linux runners (AppImage runtime dep on Ubuntu 22.04).
  - Replaced broken `if: env.APPLE_CERT_P12 != ''` with a `Detect Apple cert availability` step that writes `have_cert=true|false` to `$GITHUB_OUTPUT`, and gates both the cert-import step and the build-step's `CSC_IDENTITY_AUTO_DISCOVERY` env on that output.
  - When no Apple cert is configured, `CSC_IDENTITY_AUTO_DISCOVERY=false` skips the keychain search entirely so unsigned macOS builds succeed.

**Verification:**
- Playwright in browser preview: Empty project on `/transactions` → 3 state transitions max (`other` → `loading` → `empty`), final state stable. Rich project on `/transactions` → all 3 imported transactions visible by data-testid. Empty project on `/recurring` → 2 state transitions, no flash.
- Backend regression: **115 passed / 1 skipped / 0 failed**.

### Iteration 14 (2026-02-13) — State-management hardening: project switch / delete / tx delete



**Reported by user:**
> "Switching projects isn't auto-updating the pages; deleting a project doesn't work; deleting a transaction doesn't auto-update the page. The app falls over very easily — I have to close and reopen it to fix things."

**Root causes identified:**
1. Stale-response races: a slower fetch from project A could resolve after the user had already switched to project B and overwrite B's state.
2. `active = projects.find(...)` was producing new object references whenever `projects` was replaced, causing `useEffect` chains to re-run spuriously and (combined with the race above) display stale data.
3. `BankAccountProvider` cleared its selection too eagerly during the project-switch transition (the "drop invalid selection" effect fired against the *old* project's accounts list).
4. Project delete waited on `await reload()` inside `finally{}` — when `reload()` itself threw the user was left stranded on a deleted project's URL with a flashing error overlay.
5. Tx / category / project delete relied on a follow-up `load()` call; if that load fell behind, the UI rows lingered.
6. Several mutating endpoints (categorize, split, AI auto-categorize, upload) didn't notify other pages, so Dashboard summary / Reports heatmap / Budgets progress could go stale until the user navigated away and back.

**Fixes shipped:**
- **`lib/projectContext.jsx` rewrite**: memoised `active`; new `revision` counter + `bumpRevision()`; `activeIdRef` to avoid stale-closure in `reload()`; clears `localStorage.activeProjectId` when activeId becomes null; `window.focus` listener that re-reads `/api/projects` so coming back to the app refreshes data.
- **`lib/bankAccountContext.jsx`**: `fetchEpoch` ref so old project's `/bank-accounts` response can't overwrite the new one; clears `accounts` immediately on project switch; "drop invalid selection" effect now only fires after the new project's accounts have actually loaded.
- **`lib/useFetchGuard.js`** (new): tiny `guard(async ({ isStale }) => …)` hook. Wired into Dashboard, Transactions, Categories, Reports, Recurring, Budgets, BudgetSummary — every page now ignores stale responses from before the latest fetch.
- **Optimistic deletes** in Transactions (single + bulk), Categories (with child-detach), and project delete (Layout) — UI updates instantly; rolls back on failure; followed by a re-fetch to reconcile derived totals.
- **`bumpRevision()` everywhere**: tx delete / bulk-delete / unsplit / bulk-categorize / reclassify / auto-categorize, category create/edit/delete, CSV + URL imports, post-import account reassign — all now fire `bumpRevision()` so Dashboard summary / Reports / Budgets re-fetch in place.
- **`lib/api.js`**: global axios response interceptor downgrades unhandled errors from `console.error` → `console.warn` so CRA's dev error overlay no longer pops up on transient 403s during project switches / Cloudflare challenges.
- **`Layout.jsx` delete**: navigate + bumpRevision now run BEFORE `reload()`, so the user is never stranded on the deleted-project URL even if the projects refresh hiccups.
- **Project-switch UX**: removed `navigate('/')` from project-switch (kept on project-delete only) — switching now refreshes the user's CURRENT page in place instead of yanking them to Dashboard.

**Tests:**
- Pytest regression: **115 passed / 1 skipped / 0 failed** in 116.81s. No backend changes.
- Frontend e2e (`/app/test_reports/iteration_14.json`): P0 in-place project refresh, rapid switching, and empty-state clearing all confirmed working end-to-end via Playwright. Project-delete + tx-delete partially verified manually before Cloudflare bot-protection started 403-ing the in-page fetches mid-test; the two robustness fixes above were applied off the back of the tester's action items.

### Iteration 13 (2026-02-12) — Theming engine + UI polish sweep + expanded category palette

**User ask:** sweep ALL pages for visual consistency + micro-interactions + density, add more colour options for categories, add multiple selectable themes.

**Theming engine:**
- New `lib/themeContext.jsx` (`ThemeProvider`, `useTheme`, `THEMES`) + `lib/useThemeColors.js` hook that resolves CSS variables into literal hex for Recharts SVG attributes (with a `MutationObserver` on `data-theme` so charts re-paint on theme switch).
- 4 production-quality themes selectable on Settings: **Sage** (warm earth, default), **Midnight** (deep slate + emerald, dark), **Ocean** (cool light blue/teal), **Aurora** (deep violet, dark). Each ships with a 4-swatch preview card and a `light`/`dark` pill.
- Choice persisted to `localStorage("ledgerly.theme")`, applied via `<html data-theme="…">` + `dark` class for shadcn primitives.
- `index.css` now defines `--c-bg / --c-bg-alt / --c-card / --c-surface / --c-border / --c-ink / --c-muted / --c-muted-2 / --c-primary / --c-primary-deep / --c-primary-soft / --c-success / --c-danger / --c-danger-deep / --c-accent / --c-accent-2 / --c-warn / --c-on-primary` for every theme, plus shadcn HSL surfaces kept in sync.

**Global polish (index.css):**
- Smooth 200ms theme transitions on body, 150ms hover/focus transitions on every interactive element.
- `focus-visible` outline ring tied to `--c-primary` (45% mix).
- Reusable `ledger-fade-in` (page entrance), `ledger-skeleton` (shimmer), `ledger-card` (hover lift), themed `.scrollbar-thin` and grain background.

**Mass migration:**
- Bulk-replaced ~600+ hardcoded hex literals across every page + non-shadcn component with `var(--c-*)` references.
- Converted `bg-[var(--c-X)]/N` / `border-[var(--c-X)]/N` / `text-[var(--c-X)]/N` patterns to `color-mix(in_srgb, var(--c-X) N%, transparent)` because Tailwind's slash-opacity syntax doesn't apply to CSS vars.
- Replaced literal `bg-white` and `text-white` with theme-aware `bg-[var(--c-card)]` / `text-[var(--c-on-primary)]`.
- Recharts (`Dashboard.jsx`) now reads palette from `useThemeColors()` so bars/cells/tooltip background follow the active theme.

**Expanded category palette:**
- New `components/ColorPicker.jsx` exporting `CATEGORY_COLORS` — 40 curated colours grouped by hue family (greens, teals, blues, purples, pinks, ambers, browns, neutrals) in a 10-column grid with hover-scale + ring-marked selection.
- Categories page create/edit dialog now uses the picker (`data-testid="category-color-picker"` + per-swatch `data-testid="color-<hex>"`).

**Polish primitives ready for future iterations:**
- `components/Skeleton.jsx` (shimmering placeholder + `<SkeletonLines>`)
- `components/EmptyState.jsx` (icon-circle + title + description + optional action)

**Tests:**
- Pytest regression: **115/116 passing, 1 skipped, 0 failed** (no API changes).
- Frontend e2e via testing agent: theme picker round-trips through localStorage + reload, all 8 pages render in both light & dark, new ColorPicker round-trips a chosen colour through `POST /api/categories` → `GET /api/categories`.
- Report: `/app/test_reports/iteration_13.json` (100% success).

### Iteration 12 (2026-02-08) — Split transactions + AI-assisted detection

**Why:** A single bank transaction (e.g. £80 supermarket = £50 groceries + £30 fuel) couldn't be attributed to multiple categories without inflating totals.

**Backend:**
- New `parent_transaction_id` + `is_split` columns on `transactions` (auto-migrated).
- `SplitLine` + `SplitPayload` models.
- `POST /api/transactions/{id}/split` — validates: ≥2 lines, sign matches parent, sum equals parent within £0.01. Sets parent `is_split=True`, creates children with `parent_transaction_id`, assigns sequential `time` per (project, account, date).
- `DELETE /api/transactions/{id}/split` — un-split: deletes children, flips parent back to `is_split=False`.
- `GET /api/transactions/{id}/splits` — list children for a parent.
- `GET /api/transactions` excludes `is_split=true` parents by default; `?include_split_parents=true` opts back in.
- `/api/analytics/yearly`, `/api/analytics/recurring`, `/api/budgets/progress` all filter out `is_split=true` parents so split children represent the spend without double-counting.
- **AI-assisted:** new `POST /api/transactions/detect-splits` walks the user's transactions ≥£25, asks the configured LLM to flag those covering multiple categories, returns candidate `{transaction, splits[{category_id, category_name, category_known, amount, reason}], reason, auto_balanced, provider}`. Nothing mutated.

**Frontend:**
- New `SplitDialog` — manual editor with running "remaining" counter (green "Balanced" badge / red "Remaining: £X"), per-line balance-to button, add/remove lines, Save disabled until balanced + every line categorised.
- New `SplitReviewDialog` — walks AI candidates **one at a time**. For each: shows merchant + amount + AI reasoning + suggested split lines + 4 buttons (Prev / Skip / Edit / Confirm). Confirm is disabled unless ≥2 of the suggested lines map to existing categories. "Edit before applying" pops the regular SplitDialog pre-seeded with AI lines so the user can edit before saving. Final toast: "X applied · Y skipped".
- Transactions page: scissors split button per row, X unsplit button on parents, "Split into N" chip with line-through amount, expand arrow to reveal indented child rows inline, "Show split parent rows" toggle, "AI: detect splits" toolbar button.
- `auto_balanced` flag surfaced from `detect_splits` — review dialog warns when the AI's last line was rounded.

**Tests:**
- New `/app/backend/tests/test_iteration12_splits.py` — 10 cases (happy path, all 5 validation errors, hidden-by-default + opt-in, unsplit, analytics excludes parent, budgets roll up from children only, detect-splits endpoint exists).
- Result: **10/10 new + 105 regression = 115/116 passing** (1 pre-existing skip).
- Frontend self-verified end-to-end: 20-row Nationwide PDF uploaded → scissors button visible on every row → click opens SplitDialog with parent pre-split into 2 lines, "Balanced" badge green, Save disabled until categories picked. AI button live in toolbar.

### Iteration 11 (2026-02-08) — Bank accounts, sub-categories, time-of-day, group-by, heatmap fix

**Yearly Report color fix.** Monthly cell text now always renders dark (#1F2E1B) on a low-opacity tint (≤30%); fixes the unreadable numbers on lighter months.

**Bank accounts (full new domain):**
- New `bank_accounts` SQLite table with auto-migration via `PRAGMA table_info` + `ALTER ADD COLUMN`.
- `models.BankAccount/Create/Update` plus `bank_account_id` on `Transaction`.
- `routes/bank_accounts.py`: full CRUD; UK sort-code regex (`12-34-56` and variants); 409 on duplicates within a project; delete detaches transactions (sets `bank_account_id` NULL).
- **Upload auto-detection**: PDF upload extracts text from first 2 pages, finds the sort code, picks/creates a matching `BankAccount`, attaches it to all imported rows. Recognises Nationwide, Bank of Scotland, Lloyds, Monzo, Starling, Barclays, HSBC, Santander, NatWest, First Direct, Revolut, Halifax.
- **Cascade**: `delete_project` cleans up `bank_accounts`.

**Time of day on transactions:**
- New `time` column on `transactions`.
- `_next_time_for_date()` auto-assigns sequential `00:00:01`, `00:00:02`, … per (project, account, date) on import so duplicates / order is preserved.
- Transactions UI: time renders below the date in small tabular-nums when present.

**Global bank filter pill:**
- New `BankAccountProvider` context, per-project localStorage key (`ledgerly.bankFilter:<project_id>`); survives page navigations + reloads.
- New `BankAccountFilter` header pill component using Radix `DropdownMenu` + radio group.
- Applied to: GET `/transactions`, `/analytics/yearly`, Transactions page, Reports page, Dashboard.
- Empty state: 'No accounts yet' chip (no upload yet).

**Day / Week / Month grouping on Transactions:**
- New `groupMode` state with toggle buttons (data-testids `group-flat/day/week/month`).
- Per-group header row shows label + tx count + net total in green/red.

**Sub-categories (one level deep, with roll-up):**
- `Category.parent_id` added; POST/PUT validate that a sub-cat's parent is itself top-level.
- `delete_category` detaches children (sets `parent_id` NULL) instead of cascade-deleting.
- `analytics/yearly` rolls each child's totals into its root for the headline breakdown.
- `budgets/progress` walks the parent chain and counts a child transaction toward every ancestor budget.
- Categories page: tree view with indented children and an inline `+` to add a sub-category with the parent pre-selected. New Category dialog gets a parent picker.

**Tests:**
- New `/app/backend/tests/test_iteration11_bank_subcat.py` — 15 cases (CRUD, 409 duplicates, PDF auto-detect, sub-category one-level enforcement, budget roll-up).
- Result: **15/15 new + 90 regression = 105/106 passing** (1 pre-existing skip).
- Frontend e2e: **19/19 user-visible checkpoints** validated against the public preview URL.

### Iteration 10 (2026-02-08) — Real-world PDF parser fixes

**Two real UK bank statements were failing**:
1. **Nationwide FlexBasic**: parsed 0–8 rows instead of 20. PDF splits the table across multiple `pdfplumber` tables on the same page (only the first has a header), transactions span multiple rows (continuation lines), and dates like "09 Feb" lack a year.
2. **Bank of Scotland**: parsed 0 rows. PDF text layer has overlapping fragments that interleave column headers into cell data — every row reads like `D0ate 2 Jan 26 DPescription POINT_*KENILWORTH TDype EB Moneyb Ilna n(k£.) 23.98Money Out (£)`.

**Fixes (all in `services/parsers.py`):**
- `_infer_year()` — pulls the statement year from several UK statement header patterns ("Statementdate: 04 March 2026", "01 January 2026 to 31 January 2026", etc.).
- `_parse_pdf_tables_with_continuation()` — header-less continuation tables on the same page inherit the previous table's column indices; description-only continuation rows append to the current transaction; date-bearing rows inherit the year from the statement header.
- `_parse_bos_text()` + `_BOS_ROW` — specialised regex captures the leaked first character of each cell (`D{X}ate`, `D{Y}escription`, `T{Z}ype`) and re-attaches them, with smart de-dup so "P"+"POINT" doesn't become "PPOINT".
- `_parse_pdf_text_lines()` — generic UK-line-format fallback (`<DD Mon> <desc> <amount> <opt balance>`); catches transactions tables miss entirely, infers expense/income sign from keywords ("direct debit", "bank credit", etc.).
- `_dedupe_rows()` — combines table + text-line results without double-counting; prefers the longer description (tables are usually richer).

**Result on the user-supplied statements:**
- Nationwide: **20 transactions parsed, net £-501.56 — exactly matches start£1,007.05 → end £505.49**.
- Bank of Scotland: **70 transactions parsed**, all descriptions reconstructed correctly (ASDA STORES, TESCO STORES, VANQUIS BANK, MARKS&SPENCER, MATHEW MCNEE, etc.), income vs expense signs correct (FUTURESE LTD salary positive, CAPITAL ONE payment negative).

**Tests:**
- New `/app/backend/tests/fixtures/{nationwide_mar2026,bos_jan2026}.pdf` pinned.
- New `/app/backend/tests/test_iteration10_real_pdfs.py` — 9 cases (row counts, balance math, key transactions, sign correctness, first-letter recovery, multi-day date decoding).
- Result: **9/9 new + 81/82 regression = 90/91 passing** (1 pre-existing skip).
