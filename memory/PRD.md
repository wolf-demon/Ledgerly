# Ledgerly — Personal Finance Categorizer

## Original Problem Statement
Web app to import monthly bank statements (CSV/PDF), categorize transactions into income/expense groups, learn rules so recurring merchants auto-classify, and visualize yearly/monthly breakdowns. Multiple projects (e.g. Personal, Business). Currency: GBP. No login.

## Architecture
- **Frontend**: React 19 + TailwindCSS + Shadcn UI + Recharts + Framer Motion
- **Backend**: FastAPI + Motor (MongoDB) + pandas + pdfplumber + emergentintegrations (Claude Sonnet 4.5)
- **DB collections**: projects, categories, transactions, rules

## Implemented (2026-02-08)
- Multi-project switcher with default category seeding (9 cats)
- CSV & PDF upload with auto column detection and dedupe
- AI category suggestion (Claude Sonnet 4.5 via Emergent LLM key)
- Rule learning: "Apply to similar" creates a normalized merchant rule and back-applies
- Categories CRUD with color palette
- Transactions list with search, uncategorized filter, inline categorize dialog
- Dashboard: cashflow bar chart, expense pie, summary cards (income/expense/net/savings rate), recent tx
- Yearly Report: category × month heatmap (income & expense tabs), category drill-down with monthly bars + transactions

## User Personas
- Single user with personal/business/joint household projects on one device

## Test Credentials
N/A (no auth)

## Backlog (future)
- P1: Render "Uncategorized" row in Reports heatmap explicitly
- P1: Export to CSV / multi-month PDF report
- P1: Bulk categorize selected transactions
- P2: Recurring transaction detection / forecasts
- P2: Multiple bank account merging in a single project
- P2: Electron/PWA desktop installer
