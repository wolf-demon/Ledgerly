"""Ledgerly FastAPI app.

Bootstraps the storage backend, mounts the modular API routers, configures
CORS + logging, and wires startup/shutdown hooks. All endpoint logic now
lives under `routes/` and shared logic under `services/`.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import app_db  # noqa: E402  (must run after load_dotenv)
from routes import analytics, bank_accounts, budgets, categories, categorize, projects, settings, transactions  # noqa: E402

# Backward-compat re-exports — tests and external scripts may still import these from `server`.
from services.parsers import (  # noqa: E402,F401
    detect_format,
    google_sheet_to_csv_url,
    parse_any,
    parse_csv,
    parse_excel,
    parse_ods,
    parse_ofx,
    parse_pdf,
    parse_tsv,
)
from services.helpers import (  # noqa: E402,F401
    apply_rules,
    find_column,
    force_amount_sign,
    normalize_merchant,
    parse_amount,
    parse_date,
)

app = FastAPI()
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"message": "FinanceFlow API"}


api_router.include_router(projects.router)
api_router.include_router(categories.router)
api_router.include_router(transactions.router)
api_router.include_router(settings.router)
api_router.include_router(analytics.router)
api_router.include_router(categorize.router)
api_router.include_router(budgets.router)
api_router.include_router(bank_accounts.router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup_db_client():
    await app_db.startup()


@app.on_event("shutdown")
async def shutdown_db_client():
    await app_db.shutdown()
