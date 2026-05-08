from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import io
import re
import json
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import pandas as pd
import pdfplumber
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Storage backend selection: SQLite (default for desktop) or MongoDB.
STORAGE = os.environ.get('STORAGE', 'sqlite').lower()

if STORAGE == 'mongo':
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo_url = os.environ['MONGO_URL']
    _mongo_client = AsyncIOMotorClient(mongo_url)
    db = _mongo_client[os.environ['DB_NAME']]
    _sqlite_db = None
else:
    from sqlite_db import SQLiteDB
    _default_path = str(ROOT_DIR / 'ledgerly.db')
    sqlite_path = os.environ.get('SQLITE_PATH', _default_path)
    _sqlite_db = SQLiteDB(sqlite_path)
    db = _sqlite_db
    _mongo_client = None

EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ============= MODELS =============

class Project(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProjectCreate(BaseModel):
    name: str
    description: str = ""

class Category(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    name: str
    type: str  # "income" or "expense"
    color: str = "#364C2E"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CategoryCreate(BaseModel):
    project_id: str
    name: str
    type: str
    color: str = "#364C2E"

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    type: Optional[str] = None

class Transaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    date: str  # ISO date YYYY-MM-DD
    description: str
    amount: float  # negative = expense, positive = income
    type: str  # "income" or "expense"
    category_id: Optional[str] = None
    raw_row: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class TransactionUpdate(BaseModel):
    category_id: Optional[str] = None
    description: Optional[str] = None
    apply_to_similar: bool = False  # if True, also assign to other tx with same merchant key

class CategoryRule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    pattern: str  # normalized merchant key
    category_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SuggestRequest(BaseModel):
    project_id: str
    description: str
    amount: float

# ============= HELPERS =============

def normalize_merchant(description: str) -> str:
    """Normalize merchant description for rule matching."""
    s = description.upper()
    # remove dates, ref numbers, trailing digits
    s = re.sub(r'\d{2}[/\-]\d{2}[/\-]\d{2,4}', '', s)
    s = re.sub(r'\b\d{4,}\b', '', s)
    s = re.sub(r'[^A-Z &]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # take first 3 significant words
    parts = s.split()[:3]
    return ' '.join(parts)

def parse_amount(val) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    s = s.replace(',', '').replace('£', '').replace('$', '').replace('€', '')
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1]
    if s.startswith('-'):
        neg = True
        s = s[1:]
    try:
        v = float(s)
        return -v if neg else v
    except Exception:
        return None

def parse_date(val) -> Optional[str]:
    if val is None:
        return None
    try:
        dt = pd.to_datetime(val, dayfirst=True, errors='coerce')
        if pd.isna(dt):
            return None
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return None

def find_column(cols: List[str], keywords: List[str]) -> Optional[str]:
    for kw in keywords:
        for c in cols:
            if kw in c.lower():
                return c
    return None

def _parse_dataframe(df: "pd.DataFrame") -> List[Dict[str, Any]]:
    """Shared row-extraction logic for CSV / TSV / Excel / ODS dataframes."""
    cols = list(df.columns)
    date_col = find_column(cols, ['date', 'posted', 'transaction date'])
    desc_col = find_column(cols, ['description', 'detail', 'narrative', 'memo', 'particulars', 'reference', 'payee', 'name'])
    amount_col = find_column(cols, ['amount', 'value'])
    debit_col = find_column(cols, ['debit', 'paid out', 'withdrawal', 'money out', 'out'])
    credit_col = find_column(cols, ['credit', 'paid in', 'deposit', 'money in', 'in'])
    type_col = find_column(cols, ['dr/cr', 'cr/dr', 'transaction type', 'txn type', 'type'])

    # Avoid type_col matching the description column when banks use a column literally named "Type"
    if type_col == desc_col:
        type_col = None

    DEBIT_HINTS = {"DR", "DEBIT", "D", "OUT", "PAYMENT", "WITHDRAWAL", "PURCHASE", "POS", "ATM"}
    CREDIT_HINTS = {"CR", "CREDIT", "C", "IN", "DEPOSIT", "REFUND", "TRANSFER IN"}

    rows = []
    for _, r in df.iterrows():
        date_val = parse_date(r[date_col]) if date_col else None
        desc_val = str(r[desc_col]).strip() if desc_col and pd.notna(r[desc_col]) else ''
        amt: Optional[float] = None

        # 1) Two-column Debit/Credit takes precedence (most reliable for UK banks).
        if debit_col or credit_col:
            d = parse_amount(r[debit_col]) if debit_col else None
            c = parse_amount(r[credit_col]) if credit_col else None
            if d is not None and d != 0:
                amt = -abs(d)
            elif c is not None and c != 0:
                amt = abs(c)

        # 2) Single Amount column — apply Type column hint if amount is unsigned.
        if amt is None and amount_col:
            raw = parse_amount(r[amount_col])
            if raw is not None:
                if type_col:
                    type_val = str(r[type_col] or '').strip().upper()
                    # Normalize so "DEBIT CARD PURCHASE" -> "DEBIT", etc.
                    type_token = next((tok for tok in type_val.split() if tok in DEBIT_HINTS or tok in CREDIT_HINTS), type_val)
                    if type_token in DEBIT_HINTS:
                        amt = -abs(raw)
                    elif type_token in CREDIT_HINTS:
                        amt = abs(raw)
                    else:
                        amt = raw  # keep sign as-is
                else:
                    amt = raw

        if not date_val or not desc_val or amt is None:
            continue
        rows.append({"date": date_val, "description": desc_val, "amount": amt})
    return rows

def parse_csv(content: bytes, sep: str = ",") -> List[Dict[str, Any]]:
    try:
        df = pd.read_csv(io.BytesIO(content), sep=sep)
    except Exception:
        df = pd.read_csv(io.BytesIO(content), sep=sep, encoding='latin-1')
    return _parse_dataframe(df)

def parse_tsv(content: bytes) -> List[Dict[str, Any]]:
    return parse_csv(content, sep="\t")

def parse_excel(content: bytes) -> List[Dict[str, Any]]:
    """Parses .xlsx (openpyxl) and .xls (xlrd). Tries each sheet, returns the first that yields rows."""
    last_err = None
    for engine in ("openpyxl", "xlrd"):
        try:
            sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, engine=engine)
            for _, df in sheets.items():
                rows = _parse_dataframe(df)
                if rows:
                    return rows
            return []
        except Exception as e:
            last_err = e
            continue
    raise ValueError(f"Could not read Excel file: {last_err}")

def parse_ods(content: bytes) -> List[Dict[str, Any]]:
    sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, engine="odf")
    for _, df in sheets.items():
        rows = _parse_dataframe(df)
        if rows:
            return rows
    return []

def parse_ofx(content: bytes) -> List[Dict[str, Any]]:
    """Open Financial Exchange — the standard format most banks export to."""
    from ofxparse import OfxParser
    ofx = OfxParser.parse(io.BytesIO(content))
    rows = []
    for acct in getattr(ofx, "accounts", []) or []:
        statement = getattr(acct, "statement", None)
        if not statement:
            continue
        for tx in getattr(statement, "transactions", []) or []:
            try:
                date_val = tx.date.strftime("%Y-%m-%d") if tx.date else None
                amt = float(tx.amount) if tx.amount is not None else None
                desc = (getattr(tx, "memo", "") or getattr(tx, "payee", "") or "").strip()
                if date_val and desc and amt is not None:
                    rows.append({"date": date_val, "description": desc, "amount": amt})
            except Exception:
                continue
    return rows

def google_sheet_to_csv_url(url: str) -> Optional[str]:
    """Convert any public Google Sheets share URL into its CSV export URL."""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not m:
        return None
    sheet_id = m.group(1)
    gid_m = re.search(r"[?&#]gid=(\d+)", url)
    gid = gid_m.group(1) if gid_m else "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

# Map of supported file-type tags to their parser.
_PARSERS: Dict[str, Any] = {
    "csv": parse_csv,
    "tsv": parse_tsv,
    "pdf": None,  # filled below after parse_pdf is defined
    "xlsx": parse_excel,
    "xls": parse_excel,
    "ods": parse_ods,
    "ofx": parse_ofx,
    "qfx": parse_ofx,
}

def detect_format(filename: str, content_type: Optional[str]) -> Optional[str]:
    name = (filename or "").lower()
    ct = (content_type or "").lower()
    if name.endswith(".csv") or ct == "text/csv":
        return "csv"
    if name.endswith(".tsv") or ct in ("text/tab-separated-values", "text/tsv"):
        return "tsv"
    if name.endswith(".pdf") or ct == "application/pdf":
        return "pdf"
    if name.endswith(".xlsx") or "spreadsheetml" in ct:
        return "xlsx"
    if name.endswith(".xls") or ct == "application/vnd.ms-excel":
        return "xls"
    if name.endswith(".ods") or "opendocument.spreadsheet" in ct:
        return "ods"
    if name.endswith(".ofx") or name.endswith(".qfx") or "ofx" in ct:
        return "ofx"
    return None

def parse_any(content: bytes, filename: str, content_type: Optional[str]) -> List[Dict[str, Any]]:
    """Dispatch to the right parser based on filename/content_type, with sensible fallback chain."""
    fmt = detect_format(filename, content_type)
    parser = _PARSERS.get(fmt) if fmt else None
    if parser is not None:
        return parser(content)
    # Unknown extension: try CSV, then PDF as a last resort.
    try:
        rows = parse_csv(content)
        if rows:
            return rows
    except Exception:
        pass
    try:
        return parse_pdf(content)
    except Exception:
        return []

def parse_pdf(content: bytes) -> List[Dict[str, Any]]:
    rows = []
    text_blocks = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            # try tables first
            try:
                tables = page.extract_tables()
                for tbl in tables:
                    if not tbl or len(tbl) < 2:
                        continue
                    header = [str(h or '').lower() for h in tbl[0]]
                    date_idx = next((i for i, h in enumerate(header) if 'date' in h), None)
                    desc_idx = next((i for i, h in enumerate(header) if any(k in h for k in ['descr', 'detail', 'narr', 'partic'])), None)
                    amt_idx = next((i for i, h in enumerate(header) if 'amount' in h), None)
                    debit_idx = next((i for i, h in enumerate(header) if 'debit' in h or 'paid out' in h or 'withdraw' in h), None)
                    credit_idx = next((i for i, h in enumerate(header) if 'credit' in h or 'paid in' in h or 'deposit' in h), None)
                    for r in tbl[1:]:
                        if not r:
                            continue
                        d = parse_date(r[date_idx]) if date_idx is not None and date_idx < len(r) else None
                        desc = str(r[desc_idx]).strip() if desc_idx is not None and desc_idx < len(r) and r[desc_idx] else ''
                        amt = None
                        if amt_idx is not None and amt_idx < len(r):
                            amt = parse_amount(r[amt_idx])
                        if amt is None:
                            di = parse_amount(r[debit_idx]) if debit_idx is not None and debit_idx < len(r) else None
                            ci = parse_amount(r[credit_idx]) if credit_idx is not None and credit_idx < len(r) else None
                            if di is not None and di != 0:
                                amt = -abs(di)
                            elif ci is not None and ci != 0:
                                amt = abs(ci)
                        if d and desc and amt is not None:
                            rows.append({"date": d, "description": desc, "amount": amt})
            except Exception:
                pass
            try:
                text_blocks.append(page.extract_text() or '')
            except Exception:
                pass

    if rows:
        return rows

    # fallback regex on text
    text = "\n".join(text_blocks)
    # Pattern: date description amount
    pattern = re.compile(
        r'(\d{1,2}[\/\-\s][A-Za-z\d]{1,4}[\/\-\s]\d{2,4})\s+(.+?)\s+(-?£?\(?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?)',
    )
    for m in pattern.finditer(text):
        d = parse_date(m.group(1))
        desc = m.group(2).strip()
        amt = parse_amount(m.group(3))
        if d and desc and amt is not None:
            rows.append({"date": d, "description": desc, "amount": amt})
    return rows

# Wire parse_pdf into the dispatcher (defined after parse_pdf so we register it here).
_PARSERS["pdf"] = parse_pdf

async def apply_rules(project_id: str, description: str) -> Optional[str]:
    key = normalize_merchant(description)
    if not key:
        return None
    rule = await db.rules.find_one({"project_id": project_id, "pattern": key}, {"_id": 0})
    if rule:
        return rule.get("category_id")
    return None

# ============= ENDPOINTS =============

@api_router.get("/")
async def root():
    return {"message": "FinanceFlow API"}

# ----- Projects -----
@api_router.post("/projects", response_model=Project)
async def create_project(payload: ProjectCreate):
    proj = Project(**payload.model_dump())
    doc = proj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.projects.insert_one(doc)
    # seed default categories
    defaults = [
        ("Salary", "income", "#4B6B40"),
        ("Other Income", "income", "#728A66"),
        ("Groceries", "expense", "#D96C4E"),
        ("Rent / Mortgage", "expense", "#364C2E"),
        ("Utilities", "expense", "#D1A77E"),
        ("Transport", "expense", "#E3C8AA"),
        ("Dining", "expense", "#D96C4E"),
        ("Entertainment", "expense", "#728A66"),
        ("Shopping", "expense", "#D1A77E"),
    ]
    for name, t, color in defaults:
        cat = Category(project_id=proj.id, name=name, type=t, color=color)
        cdoc = cat.model_dump()
        cdoc['created_at'] = cdoc['created_at'].isoformat()
        await db.categories.insert_one(cdoc)
    return proj

@api_router.get("/projects", response_model=List[Project])
async def list_projects():
    docs = await db.projects.find({}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    for d in docs:
        if isinstance(d.get('created_at'), str):
            d['created_at'] = datetime.fromisoformat(d['created_at'])
    return docs

@api_router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    await db.projects.delete_one({"id": project_id})
    await db.categories.delete_many({"project_id": project_id})
    await db.transactions.delete_many({"project_id": project_id})
    await db.rules.delete_many({"project_id": project_id})
    return {"ok": True}

# ----- Categories -----
@api_router.get("/categories", response_model=List[Category])
async def list_categories(project_id: str):
    docs = await db.categories.find({"project_id": project_id}, {"_id": 0}).to_list(1000)
    for d in docs:
        if isinstance(d.get('created_at'), str):
            d['created_at'] = datetime.fromisoformat(d['created_at'])
    return docs

@api_router.post("/categories", response_model=Category)
async def create_category(payload: CategoryCreate):
    if payload.type not in ("income", "expense"):
        raise HTTPException(status_code=400, detail="type must be 'income' or 'expense'")
    cat = Category(**payload.model_dump())
    doc = cat.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.categories.insert_one(doc)
    return cat

@api_router.put("/categories/{category_id}", response_model=Category)
async def update_category(category_id: str, payload: CategoryUpdate):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if update:
        await db.categories.update_one({"id": category_id}, {"$set": update})
    doc = await db.categories.find_one({"id": category_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Category not found")
    if isinstance(doc.get('created_at'), str):
        doc['created_at'] = datetime.fromisoformat(doc['created_at'])
    return doc

@api_router.delete("/categories/{category_id}")
async def delete_category(category_id: str):
    await db.categories.delete_one({"id": category_id})
    await db.transactions.update_many({"category_id": category_id}, {"$set": {"category_id": None}})
    await db.rules.delete_many({"category_id": category_id})
    return {"ok": True}

# ----- Transactions -----
async def _ingest_rows(project_id: str, rows: List[Dict[str, Any]]) -> Dict[str, int]:
    inserted = 0
    skipped = 0
    for r in rows:
        existing = await db.transactions.find_one({
            "project_id": project_id,
            "date": r["date"],
            "description": r["description"],
            "amount": r["amount"],
        })
        if existing:
            skipped += 1
            continue
        ttype = "income" if r["amount"] >= 0 else "expense"
        cat_id = await apply_rules(project_id, r["description"])
        tx = Transaction(
            project_id=project_id,
            date=r["date"],
            description=r["description"],
            amount=r["amount"],
            type=ttype,
            category_id=cat_id,
        )
        doc = tx.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        await db.transactions.insert_one(doc)
        inserted += 1
    return {"inserted": inserted, "skipped": skipped, "total": len(rows)}

@api_router.post("/transactions/upload")
async def upload_statement(project_id: str = Form(...), file: UploadFile = File(...)):
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    content = await file.read()
    try:
        rows = parse_any(content, file.filename or "", file.content_type)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse file: {e}")
    if not rows:
        raise HTTPException(
            status_code=400,
            detail="No transactions found. Supported: CSV, TSV, PDF, Excel (.xlsx/.xls), OpenDocument (.ods), OFX/QFX.",
        )
    return await _ingest_rows(project_id, rows)

class UrlImportPayload(BaseModel):
    project_id: str
    url: str

@api_router.post("/transactions/import-url")
async def import_from_url(payload: UrlImportPayload):
    """Import transactions from a public URL. Specifically supports Google Sheets share links."""
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    fetch_url = google_sheet_to_csv_url(payload.url) or payload.url
    is_gsheet = "spreadsheets/d/" in payload.url

    import requests
    try:
        resp = requests.get(fetch_url, timeout=30, allow_redirects=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not fetch URL: {e}")
    if resp.status_code != 200:
        hint = (
            " — make sure the Google Sheet is shared with 'Anyone with the link'"
            if is_gsheet else ""
        )
        raise HTTPException(
            status_code=400,
            detail=f"URL returned HTTP {resp.status_code}{hint}",
        )

    content = resp.content
    # Pick a filename hint so the dispatcher routes correctly.
    if is_gsheet:
        filename_hint = "google-sheet.csv"
        ct_hint = "text/csv"
    else:
        # Use last path segment if it has an extension; else fall back to .csv
        from urllib.parse import urlparse
        path = urlparse(payload.url).path
        filename_hint = path.rsplit("/", 1)[-1] or "import.csv"
        ct_hint = resp.headers.get("Content-Type", "")

    try:
        rows = parse_any(content, filename_hint, ct_hint)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse content: {e}")
    if not rows:
        raise HTTPException(
            status_code=400,
            detail="Fetched the URL but found no transaction rows. Check the file format and column headers.",
        )
    result = await _ingest_rows(payload.project_id, rows)
    result["source"] = "google-sheets" if is_gsheet else "url"
    return result

@api_router.get("/transactions", response_model=List[Transaction])
async def list_transactions(
    project_id: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    uncategorized: Optional[bool] = None,
    limit: int = 5000,
):
    q: Dict[str, Any] = {"project_id": project_id}
    if year is not None and month is not None:
        ym = f"{year:04d}-{month:02d}"
        q["date"] = {"$regex": f"^{ym}"}
    elif year is not None:
        q["date"] = {"$regex": f"^{year:04d}"}
    if uncategorized:
        q["category_id"] = None
    docs = await db.transactions.find(q, {"_id": 0}).sort("date", -1).to_list(limit)
    for d in docs:
        if isinstance(d.get('created_at'), str):
            d['created_at'] = datetime.fromisoformat(d['created_at'])
    return docs

@api_router.put("/transactions/{tx_id}")
async def update_transaction(tx_id: str, payload: TransactionUpdate):
    tx = await db.transactions.find_one({"id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    update: Dict[str, Any] = {}
    if payload.category_id is not None:
        update["category_id"] = payload.category_id
        # Force amount sign + tx type to match the category's type.
        cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
        if cat:
            update["type"] = cat["type"]
            cur_amt = float(tx.get("amount", 0))
            if cat["type"] == "expense" and cur_amt > 0:
                update["amount"] = -abs(cur_amt)
            elif cat["type"] == "income" and cur_amt < 0:
                update["amount"] = abs(cur_amt)
    if payload.description is not None:
        update["description"] = payload.description
    if update:
        await db.transactions.update_one({"id": tx_id}, {"$set": update})

    affected_similar = 0
    if payload.apply_to_similar and payload.category_id:
        key = normalize_merchant(tx["description"])
        if key:
            existing_rule = await db.rules.find_one({"project_id": tx["project_id"], "pattern": key})
            if existing_rule:
                await db.rules.update_one(
                    {"project_id": tx["project_id"], "pattern": key},
                    {"$set": {"category_id": payload.category_id}},
                )
            else:
                rule = CategoryRule(
                    project_id=tx["project_id"], pattern=key, category_id=payload.category_id
                )
                rdoc = rule.model_dump()
                rdoc['created_at'] = rdoc['created_at'].isoformat()
                await db.rules.insert_one(rdoc)
            # apply to all matching, fixing sign too
            cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
            cat_type = cat["type"] if cat else None
            all_tx = await db.transactions.find(
                {"project_id": tx["project_id"]}, {"_id": 0}
            ).to_list(10000)
            for t in all_tx:
                if normalize_merchant(t["description"]) == key and t.get("category_id") != payload.category_id:
                    sub_update: Dict[str, Any] = {"category_id": payload.category_id}
                    if cat_type:
                        sub_update["type"] = cat_type
                        cur = float(t.get("amount", 0))
                        if cat_type == "expense" and cur > 0:
                            sub_update["amount"] = -abs(cur)
                        elif cat_type == "income" and cur < 0:
                            sub_update["amount"] = abs(cur)
                    await db.transactions.update_one({"id": t["id"]}, {"$set": sub_update})
                    affected_similar += 1
    return {"ok": True, "affected_similar": affected_similar}

@api_router.delete("/transactions/{tx_id}")
async def delete_transaction(tx_id: str):
    await db.transactions.delete_one({"id": tx_id})
    return {"ok": True}

@api_router.post("/transactions/reclassify")
async def reclassify_transactions(project_id: str = Query(...)):
    """Repair transaction signs + types.
    - For categorized transactions: sign + type follow the assigned category's type.
    - For uncategorized: type is derived from the current amount sign.
    Useful after fixing parser bugs that produced wrong-signed amounts.
    """
    cats = await db.categories.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    cat_type = {c["id"]: c["type"] for c in cats}
    txs = await db.transactions.find({"project_id": project_id}, {"_id": 0}).to_list(100000)
    fixed = 0
    for t in txs:
        cur_amt = float(t.get("amount", 0))
        cid = t.get("category_id")
        update: Dict[str, Any] = {}
        if cid and cid in cat_type:
            target = cat_type[cid]
            if target == "expense" and cur_amt > 0:
                update["amount"] = -abs(cur_amt)
            elif target == "income" and cur_amt < 0:
                update["amount"] = abs(cur_amt)
            if t.get("type") != target:
                update["type"] = target
        else:
            correct = "income" if cur_amt >= 0 else "expense"
            if t.get("type") != correct:
                update["type"] = correct
        if update:
            await db.transactions.update_one({"id": t["id"]}, {"$set": update})
            fixed += 1
    return {"checked": len(txs), "fixed": fixed}

# ----- Settings -----
class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ai_provider: str = "emergent"          # "emergent" | "ollama" | "none"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    emergent_key: str = ""                  # Optional override for the Emergent LLM key.

class SettingsUpdate(BaseModel):
    ai_provider: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    emergent_key: Optional[str] = None

SETTINGS_ID = "default"

async def _get_settings() -> AppSettings:
    doc = await db.settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    if not doc:
        return AppSettings()
    return AppSettings(**{k: v for k, v in doc.items() if k in AppSettings.model_fields})

async def _save_settings(settings: AppSettings):
    existing = await db.settings.find_one({"id": SETTINGS_ID}, {"_id": 0})
    payload = settings.model_dump()
    payload["id"] = SETTINGS_ID
    payload["created_at"] = (existing or {}).get("created_at") or datetime.now(timezone.utc).isoformat()
    if existing:
        await db.settings.update_one({"id": SETTINGS_ID}, {"$set": payload})
    else:
        await db.settings.insert_one(payload)

@api_router.get("/settings", response_model=AppSettings)
async def get_settings():
    return await _get_settings()

@api_router.put("/settings", response_model=AppSettings)
async def update_settings(payload: SettingsUpdate):
    current = await _get_settings()
    new_data = current.model_dump()
    for k, v in payload.model_dump(exclude_none=True).items():
        new_data[k] = v
    if new_data["ai_provider"] not in ("emergent", "ollama", "none"):
        raise HTTPException(status_code=400, detail="ai_provider must be one of: emergent, ollama, none")
    new_settings = AppSettings(**new_data)
    await _save_settings(new_settings)
    return new_settings

@api_router.post("/settings/test-ollama")
async def test_ollama(payload: SettingsUpdate):
    """Pings an Ollama server. Returns reachable + list of installed models."""
    import requests as _req
    url = (payload.ollama_url or "http://localhost:11434").rstrip("/")
    try:
        r = _req.get(f"{url}/api/tags", timeout=4)
    except _req.exceptions.ConnectionError:
        return {
            "reachable": False,
            "error": (
                "Could not reach Ollama. Make sure Ollama is installed and running. "
                "Download from https://ollama.com/download, then run `ollama serve` if it isn't already."
            ),
        }
    except Exception as e:
        return {"reachable": False, "error": f"Connection error: {e}"}
    if r.status_code != 200:
        return {"reachable": False, "error": f"Ollama responded HTTP {r.status_code}"}
    try:
        models = [m.get("name", "") for m in r.json().get("models", [])]
    except Exception:
        models = []
    return {"reachable": True, "models": models}

@api_router.post("/settings/test-emergent")
async def test_emergent(payload: SettingsUpdate):
    """Verifies the Emergent LLM key (or the bundled env key) by issuing a tiny chat request."""
    key = (payload.emergent_key or "").strip() or EMERGENT_LLM_KEY
    if not key:
        return {"reachable": False, "error": "No key set. Paste your Emergent LLM key, or leave blank to use the bundled key."}
    try:
        chat = LlmChat(
            api_key=key,
            session_id=f"test-{uuid.uuid4()}",
            system_message="Reply with the single word OK.",
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        resp = await chat.send_message(UserMessage(text="ping"))
        text = (resp if isinstance(resp, str) else str(resp)).strip()[:80]
        return {"reachable": True, "sample": text}
    except Exception as e:
        msg = str(e)
        return {"reachable": False, "error": f"Emergent key test failed: {msg[:200]}"}

# ----- AI Suggestion -----
async def _suggest_via_emergent(sys_msg: str, user_text: str, key: str) -> str:
    chat = LlmChat(
        api_key=key,
        session_id=f"cat-{uuid.uuid4()}",
        system_message=sys_msg,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")
    resp = await chat.send_message(UserMessage(text=user_text))
    return resp.strip() if isinstance(resp, str) else str(resp)

def _suggest_via_ollama(sys_msg: str, user_text: str, url: str, model: str) -> str:
    import requests as _req
    r = _req.post(
        f"{url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    content = (data.get("message") or {}).get("content", "")
    return content.strip() if isinstance(content, str) else str(content)

@api_router.post("/categorize/suggest")
async def suggest_category(payload: SuggestRequest):
    cats = await db.categories.find({"project_id": payload.project_id}, {"_id": 0}).to_list(500)
    if not cats:
        return {"suggested_category_id": None, "suggested_name": None, "reason": "No categories defined."}
    expected_type = "income" if payload.amount >= 0 else "expense"
    candidates = [c for c in cats if c.get("type") == expected_type] or cats
    cat_list = "\n".join([f"- {c['name']}" for c in candidates])

    settings = await _get_settings()
    provider = settings.ai_provider

    if provider == "none":
        return {"suggested_category_id": None, "suggested_name": None, "reason": "AI suggestions disabled in Settings."}
    emergent_key = (settings.emergent_key or "").strip() or EMERGENT_LLM_KEY
    if provider == "emergent" and not emergent_key:
        return {"suggested_category_id": None, "suggested_name": None, "reason": "No Emergent LLM key configured. Open Settings to paste your key."}

    sys_msg = (
        "You are a personal finance assistant. Given a bank transaction description and amount, "
        "pick the single best matching category from a provided list. "
        "Respond ONLY with strict JSON of the form {\"category_name\": \"<name>\", \"reason\": \"<short reason>\"}. "
        "The category_name MUST exactly match one of the provided category names."
    )
    user_text = (
        f"Transaction description: {payload.description}\n"
        f"Amount: {payload.amount} GBP ({'income' if payload.amount >= 0 else 'expense'})\n\n"
        f"Available categories:\n{cat_list}\n\n"
        "Return JSON only."
    )

    try:
        if provider == "ollama":
            text = _suggest_via_ollama(sys_msg, user_text, settings.ollama_url, settings.ollama_model)
        else:
            text = await _suggest_via_emergent(sys_msg, user_text, emergent_key)
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            name = parsed.get("category_name", "").strip()
            reason = parsed.get("reason", "")
            clean = re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()
            for c in candidates:
                if c["name"].lower() == clean.lower() or c["name"].lower() == name.lower():
                    return {
                        "suggested_category_id": c["id"],
                        "suggested_name": c["name"],
                        "reason": reason,
                        "provider": provider,
                    }
        return {"suggested_category_id": None, "suggested_name": None, "reason": (text or "")[:200], "provider": provider}
    except Exception as e:
        logging.exception("LLM suggest failed (%s)", provider)
        msg = str(e)
        # Friendly message for the most common Ollama error: model not pulled.
        if provider == "ollama" and ("model" in msg.lower() and ("not found" in msg.lower() or "pull" in msg.lower())):
            msg = f"Ollama model '{settings.ollama_model}' not installed. Run `ollama pull {settings.ollama_model}` and try again."
        return {"suggested_category_id": None, "suggested_name": None, "reason": f"AI error: {msg[:200]}", "provider": provider}

# ----- Batch AI categorization (auto-creates new categories) -----
PALETTE = ["#364C2E", "#4B6B40", "#728A66", "#D96C4E", "#D1A77E", "#E3C8AA", "#8B5E3C", "#9E7B58"]

class BulkSuggestPayload(BaseModel):
    project_id: str
    only_uncategorized: bool = True
    allow_create: bool = True
    max_items: int = 200

@api_router.post("/transactions/bulk-suggest")
async def bulk_suggest(payload: BulkSuggestPayload):
    """Run the configured AI provider over many transactions in one go.
    Optionally creates new categories when none of the existing ones fit.
    """
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = await _get_settings()
    provider = settings.ai_provider
    if provider == "none":
        raise HTTPException(status_code=400, detail="AI provider is set to Disabled. Open Settings to enable Emergent or Ollama.")
    emergent_key = (settings.emergent_key or "").strip() or EMERGENT_LLM_KEY
    if provider == "emergent" and not emergent_key:
        raise HTTPException(status_code=400, detail="No Emergent LLM key configured. Open Settings to paste your key.")

    cats = await db.categories.find({"project_id": payload.project_id}, {"_id": 0}).to_list(500)
    if not cats and not payload.allow_create:
        raise HTTPException(status_code=400, detail="No categories defined and allow_create is false.")

    q: Dict[str, Any] = {"project_id": payload.project_id}
    if payload.only_uncategorized:
        q["category_id"] = None
    txs = await db.transactions.find(q, {"_id": 0}).to_list(payload.max_items)
    if not txs:
        return {"processed": 0, "categorized": 0, "created_categories": [], "errors": []}

    # Group by normalized merchant key — categorize once per unique merchant.
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in txs:
        k = normalize_merchant(t["description"]) or t["description"]
        groups.setdefault(k, []).append(t)

    created_categories: List[Dict[str, str]] = []
    cat_by_name: Dict[str, Dict[str, Any]] = {c["name"].lower(): c for c in cats}
    errors: List[str] = []
    categorized = 0

    sys_msg_template = (
        "You are a personal finance assistant. Pick the best category for each bank transaction. "
        "Prefer one of the EXISTING categories when reasonable. "
        "{create_hint}"
        "Respond ONLY with strict JSON of the form "
        "{{\"category_name\": \"<name>\", \"is_new\": <true|false>, \"type\": \"<income|expense>\", \"reason\": \"<short>\"}}."
    )
    create_hint = (
        "If none of the existing categories fit, you MAY suggest a brand new category — set is_new to true. "
        if payload.allow_create else
        "You MUST pick one of the existing categories — set is_new to false. "
    )
    sys_msg = sys_msg_template.format(create_hint=create_hint)

    async def _ask_ai(desc: str, amount: float) -> Optional[Dict[str, Any]]:
        existing_list = "\n".join([f"- {c['name']} ({c['type']})" for c in cat_by_name.values()]) or "(none yet)"
        user_text = (
            f"Transaction: {desc}\n"
            f"Amount: {amount} GBP ({'income' if amount >= 0 else 'expense'})\n\n"
            f"Existing categories:\n{existing_list}\n\n"
            "Return JSON only."
        )
        try:
            if provider == "ollama":
                text = _suggest_via_ollama(sys_msg, user_text, settings.ollama_url, settings.ollama_model)
            else:
                text = await _suggest_via_emergent(sys_msg, user_text, emergent_key)
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if not m:
                return None
            parsed = json.loads(m.group(0))
            name = (parsed.get("category_name") or "").strip()
            cat_type = (parsed.get("type") or "").strip().lower()
            is_new = bool(parsed.get("is_new"))
            if not name:
                return None
            if cat_type not in ("income", "expense"):
                cat_type = "income" if amount >= 0 else "expense"
            return {"name": name, "type": cat_type, "is_new": is_new, "reason": parsed.get("reason", "")}
        except Exception as e:
            errors.append(f"{desc[:40]}: {str(e)[:80]}")
            return None

    async def _resolve_category(name: str, cat_type: str, allow_new: bool) -> Optional[Dict[str, Any]]:
        clean = re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()
        existing = cat_by_name.get(clean.lower()) or cat_by_name.get(name.lower())
        if existing:
            return existing
        if not allow_new:
            return None
        # Create
        color = PALETTE[len(cat_by_name) % len(PALETTE)]
        cat = Category(project_id=payload.project_id, name=clean, type=cat_type, color=color)
        cdoc = cat.model_dump()
        cdoc['created_at'] = cdoc['created_at'].isoformat()
        await db.categories.insert_one(cdoc)
        created = {"id": cat.id, "name": cat.name, "type": cat.type, "color": cat.color, "project_id": payload.project_id}
        cat_by_name[clean.lower()] = created
        created_categories.append({"id": cat.id, "name": cat.name, "type": cat.type})
        return created

    for key, members in groups.items():
        sample = members[0]
        suggestion = await _ask_ai(sample["description"], float(sample["amount"]))
        if not suggestion:
            continue
        cat = await _resolve_category(suggestion["name"], suggestion["type"], payload.allow_create)
        if not cat:
            continue
        # Apply to all members of the group
        for t in members:
            cur = float(t.get("amount", 0))
            new_amt = cur
            if cat["type"] == "expense" and cur > 0:
                new_amt = -abs(cur)
            elif cat["type"] == "income" and cur < 0:
                new_amt = abs(cur)
            await db.transactions.update_one(
                {"id": t["id"]},
                {"$set": {"category_id": cat["id"], "type": cat["type"], "amount": new_amt}},
            )
            categorized += 1
        # Persist as a rule so future imports auto-classify too
        existing_rule = await db.rules.find_one({"project_id": payload.project_id, "pattern": key})
        if existing_rule:
            await db.rules.update_one(
                {"project_id": payload.project_id, "pattern": key},
                {"$set": {"category_id": cat["id"]}},
            )
        else:
            rule = CategoryRule(project_id=payload.project_id, pattern=key, category_id=cat["id"])
            rdoc = rule.model_dump()
            rdoc['created_at'] = rdoc['created_at'].isoformat()
            await db.rules.insert_one(rdoc)

    return {
        "processed": len(txs),
        "categorized": categorized,
        "created_categories": created_categories,
        "errors": errors[:10],
        "provider": provider,
    }

# ----- Analytics -----
@api_router.get("/analytics/yearly")
async def analytics_yearly(project_id: str, year: int):
    cats = await db.categories.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    cat_map = {c["id"]: c for c in cats}
    txs = await db.transactions.find(
        {"project_id": project_id, "date": {"$regex": f"^{year:04d}"}}, {"_id": 0}
    ).to_list(50000)

    # monthly totals
    monthly_income = [0.0] * 12
    monthly_expense = [0.0] * 12
    # category x month - split uncategorized into income / expense buckets
    cat_monthly: Dict[str, List[float]] = {c["id"]: [0.0] * 12 for c in cats}
    cat_monthly["__uncat_income__"] = [0.0] * 12
    cat_monthly["__uncat_expense__"] = [0.0] * 12
    cat_yearly: Dict[str, float] = {c["id"]: 0.0 for c in cats}
    cat_yearly["__uncat_income__"] = 0.0
    cat_yearly["__uncat_expense__"] = 0.0

    for t in txs:
        try:
            m = int(t["date"][5:7]) - 1
        except Exception:
            continue
        amt = float(t["amount"])
        if amt >= 0:
            monthly_income[m] += amt
        else:
            monthly_expense[m] += abs(amt)
        if t.get("category_id"):
            cid = t["category_id"]
        else:
            cid = "__uncat_income__" if amt >= 0 else "__uncat_expense__"
        if cid not in cat_monthly:
            cat_monthly[cid] = [0.0] * 12
            cat_yearly[cid] = 0.0
        cat_monthly[cid][m] += amt
        cat_yearly[cid] += amt

    cat_breakdown = []
    for cid, total in cat_yearly.items():
        if total == 0 and not any(cat_monthly[cid]):
            continue
        if cid == "__uncat_income__":
            cat_breakdown.append({
                "category_id": None,
                "name": "Uncategorized",
                "type": "income",
                "color": "#999999",
                "total": round(total, 2),
                "monthly": [round(v, 2) for v in cat_monthly[cid]],
            })
        elif cid == "__uncat_expense__":
            cat_breakdown.append({
                "category_id": None,
                "name": "Uncategorized",
                "type": "expense",
                "color": "#999999",
                "total": round(total, 2),
                "monthly": [round(v, 2) for v in cat_monthly[cid]],
            })
        else:
            c = cat_map.get(cid)
            if not c:
                continue
            cat_breakdown.append({
                "category_id": cid,
                "name": c["name"],
                "type": c["type"],
                "color": c.get("color", "#364C2E"),
                "total": round(total, 2),
                "monthly": [round(v, 2) for v in cat_monthly[cid]],
            })

    return {
        "year": year,
        "monthly_income": [round(v, 2) for v in monthly_income],
        "monthly_expense": [round(v, 2) for v in monthly_expense],
        "total_income": round(sum(monthly_income), 2),
        "total_expense": round(sum(monthly_expense), 2),
        "net": round(sum(monthly_income) - sum(monthly_expense), 2),
        "categories": cat_breakdown,
    }

@api_router.get("/analytics/category/{category_id}")
async def analytics_category_detail(category_id: str, project_id: str, year: int):
    txs = await db.transactions.find(
        {"project_id": project_id, "category_id": category_id, "date": {"$regex": f"^{year:04d}"}},
        {"_id": 0},
    ).sort("date", -1).to_list(10000)
    monthly = [0.0] * 12
    for t in txs:
        try:
            m = int(t["date"][5:7]) - 1
            monthly[m] += float(t["amount"])
        except Exception:
            continue
    for d in txs:
        if isinstance(d.get('created_at'), str):
            d['created_at'] = datetime.fromisoformat(d['created_at'])
    return {
        "year": year,
        "monthly": [round(v, 2) for v in monthly],
        "transactions": txs,
    }

@api_router.get("/analytics/years")
async def analytics_years(project_id: str):
    pipeline = [
        {"$match": {"project_id": project_id}},
        {"$group": {"_id": {"$substr": ["$date", 0, 4]}}},
        {"$sort": {"_id": -1}},
    ]
    years = []
    async for doc in db.transactions.aggregate(pipeline):
        try:
            years.append(int(doc["_id"]))
        except Exception:
            pass
    if not years:
        years = [datetime.now().year]
    return {"years": years}

# ----- Bulk categorize -----
class BulkCategorizePayload(BaseModel):
    transaction_ids: List[str]
    category_id: str
    apply_to_similar: bool = False

@api_router.post("/transactions/bulk-categorize")
async def bulk_categorize(payload: BulkCategorizePayload):
    if not payload.transaction_ids:
        raise HTTPException(status_code=400, detail="No transaction ids")
    target_cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
    if not target_cat:
        raise HTTPException(status_code=404, detail="Category not found")
    project_id = target_cat["project_id"]
    cat_type = target_cat["type"]

    def _signed(amt: float) -> float:
        if cat_type == "expense" and amt > 0:
            return -abs(amt)
        if cat_type == "income" and amt < 0:
            return abs(amt)
        return amt

    txs = await db.transactions.find(
        {"id": {"$in": payload.transaction_ids}, "project_id": project_id}, {"_id": 0}
    ).to_list(10000)
    # Update each tx individually so we can flip its amount sign to match category type.
    for t in txs:
        await db.transactions.update_one(
            {"id": t["id"]},
            {"$set": {
                "category_id": payload.category_id,
                "type": cat_type,
                "amount": _signed(float(t.get("amount", 0))),
            }},
        )
    rule_keys_added = 0
    similar_applied = 0
    if payload.apply_to_similar:
        keys = set()
        for t in txs:
            k = normalize_merchant(t["description"])
            if k:
                keys.add(k)
        for k in keys:
            existing_rule = await db.rules.find_one({"project_id": project_id, "pattern": k})
            if existing_rule:
                await db.rules.update_one(
                    {"project_id": project_id, "pattern": k},
                    {"$set": {"category_id": payload.category_id}},
                )
            else:
                rule = CategoryRule(project_id=project_id, pattern=k, category_id=payload.category_id)
                rdoc = rule.model_dump()
                rdoc['created_at'] = rdoc['created_at'].isoformat()
                await db.rules.insert_one(rdoc)
                rule_keys_added += 1
        all_tx = await db.transactions.find({"project_id": project_id}, {"_id": 0}).to_list(50000)
        for t in all_tx:
            if t.get("category_id") == payload.category_id:
                continue
            if normalize_merchant(t["description"]) in keys:
                await db.transactions.update_one(
                    {"id": t["id"]},
                    {"$set": {
                        "category_id": payload.category_id,
                        "type": cat_type,
                        "amount": _signed(float(t.get("amount", 0))),
                    }},
                )
                similar_applied += 1
    return {
        "updated": len(txs),
        "rules_added": rule_keys_added,
        "similar_applied": similar_applied,
    }

# ----- CSV Export -----
@api_router.get("/transactions/export")
async def export_transactions_csv(project_id: str, year: Optional[int] = None):
    from fastapi.responses import StreamingResponse
    q: Dict[str, Any] = {"project_id": project_id}
    if year is not None:
        q["date"] = {"$regex": f"^{year:04d}"}
    txs = await db.transactions.find(q, {"_id": 0}).sort("date", 1).to_list(100000)
    cats = await db.categories.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    cat_map = {c["id"]: c["name"] for c in cats}
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    proj_name = (proj or {}).get("name", "project").replace(" ", "_")

    buf = io.StringIO()
    import csv as csv_mod
    writer = csv_mod.writer(buf)
    writer.writerow(["Date", "Description", "Category", "Type", "Amount (GBP)"])
    for t in txs:
        writer.writerow([
            t["date"],
            t["description"],
            cat_map.get(t.get("category_id") or "", "Uncategorized"),
            t.get("type", ""),
            f"{float(t['amount']):.2f}",
        ])
    buf.seek(0)
    suffix = f"_{year}" if year else ""
    filename = f"{proj_name}{suffix}_transactions.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ----- Recurring detector + forecast -----
@api_router.get("/analytics/recurring")
async def analytics_recurring(project_id: str, lookback_months: int = 6):
    from collections import defaultdict
    txs = await db.transactions.find({"project_id": project_id}, {"_id": 0}).to_list(100000)
    if not txs:
        return {"recurring": [], "forecast": {"monthly_total_expense": 0.0, "monthly_total_income": 0.0}}

    cats = await db.categories.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    cat_map = {c["id"]: c for c in cats}

    # cutoff: keep last N months from latest tx
    latest = max(t["date"] for t in txs)
    latest_dt = datetime.strptime(latest, "%Y-%m-%d")
    cutoff_year = latest_dt.year
    cutoff_month = latest_dt.month - lookback_months + 1
    while cutoff_month <= 0:
        cutoff_month += 12
        cutoff_year -= 1
    cutoff = f"{cutoff_year:04d}-{cutoff_month:02d}-01"

    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in txs:
        if t["date"] < cutoff:
            continue
        key = normalize_merchant(t["description"])
        if not key:
            continue
        groups[key].append(t)

    recurring = []
    monthly_expense_forecast = 0.0
    monthly_income_forecast = 0.0

    for key, items in groups.items():
        # need at least 2 occurrences across distinct months
        months_seen = {it["date"][:7] for it in items}
        if len(months_seen) < 2:
            continue
        # average gap in days
        sorted_items = sorted(items, key=lambda x: x["date"])
        gaps = []
        for i in range(1, len(sorted_items)):
            d1 = datetime.strptime(sorted_items[i - 1]["date"], "%Y-%m-%d")
            d2 = datetime.strptime(sorted_items[i]["date"], "%Y-%m-%d")
            gaps.append((d2 - d1).days)
        avg_gap = sum(gaps) / len(gaps) if gaps else 30

        # cadence label
        if avg_gap <= 9:
            cadence = "weekly"
            occurrences_per_month = 30 / max(avg_gap, 1)
        elif avg_gap <= 18:
            cadence = "fortnightly"
            occurrences_per_month = 30 / avg_gap
        elif avg_gap <= 45:
            cadence = "monthly"
            occurrences_per_month = 1.0
        elif avg_gap <= 100:
            cadence = "quarterly"
            occurrences_per_month = 30 / avg_gap
        else:
            cadence = "irregular"
            occurrences_per_month = 30 / avg_gap

        amounts = [it["amount"] for it in items]
        avg_amount = sum(amounts) / len(amounts)
        monthly_estimate = avg_amount * occurrences_per_month
        last_seen = sorted_items[-1]["date"]
        # next expected
        next_dt = datetime.strptime(last_seen, "%Y-%m-%d")
        next_expected = (next_dt + timedelta(days=int(round(avg_gap)))).strftime("%Y-%m-%d")

        # representative description
        sample_desc = sorted_items[-1]["description"]
        cat_id = next((it.get("category_id") for it in sorted_items if it.get("category_id")), None)
        cat = cat_map.get(cat_id) if cat_id else None

        is_income = avg_amount >= 0
        recurring.append({
            "merchant_key": key,
            "sample_description": sample_desc,
            "category_id": cat_id,
            "category_name": cat["name"] if cat else "Uncategorized",
            "category_color": cat["color"] if cat else "#999999",
            "type": "income" if is_income else "expense",
            "occurrences": len(items),
            "avg_amount": round(avg_amount, 2),
            "monthly_estimate": round(monthly_estimate, 2),
            "cadence": cadence,
            "avg_gap_days": round(avg_gap, 1),
            "last_seen": last_seen,
            "next_expected": next_expected,
        })
        if is_income:
            monthly_income_forecast += monthly_estimate
        else:
            monthly_expense_forecast += abs(monthly_estimate)

    # sort by absolute monthly impact, expenses first
    recurring.sort(key=lambda r: (r["type"] != "expense", -abs(r["monthly_estimate"])))

    return {
        "lookback_months": lookback_months,
        "recurring": recurring,
        "forecast": {
            "monthly_total_expense": round(monthly_expense_forecast, 2),
            "monthly_total_income": round(monthly_income_forecast, 2),
            "monthly_net": round(monthly_income_forecast - monthly_expense_forecast, 2),
        },
    }

# ============= APP SETUP =============
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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_db_client():
    if _sqlite_db is not None:
        await _sqlite_db.connect()

@app.on_event("shutdown")
async def shutdown_db_client():
    if _mongo_client is not None:
        _mongo_client.close()
    if _sqlite_db is not None:
        await _sqlite_db.close()
