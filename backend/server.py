from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException, Query
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import io
import re
import json
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
import pandas as pd
import pdfplumber
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

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

def parse_csv(content: bytes) -> List[Dict[str, Any]]:
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception:
        df = pd.read_csv(io.BytesIO(content), encoding='latin-1')
    cols = list(df.columns)
    date_col = find_column(cols, ['date', 'posted', 'transaction date'])
    desc_col = find_column(cols, ['description', 'detail', 'narrative', 'memo', 'particulars', 'reference'])
    amount_col = find_column(cols, ['amount'])
    debit_col = find_column(cols, ['debit', 'paid out', 'withdrawal', 'money out'])
    credit_col = find_column(cols, ['credit', 'paid in', 'deposit', 'money in'])
    rows = []
    for _, r in df.iterrows():
        date_val = parse_date(r[date_col]) if date_col else None
        desc_val = str(r[desc_col]).strip() if desc_col and pd.notna(r[desc_col]) else ''
        amt = None
        if amount_col:
            amt = parse_amount(r[amount_col])
        if amt is None and (debit_col or credit_col):
            d = parse_amount(r[debit_col]) if debit_col else None
            c = parse_amount(r[credit_col]) if credit_col else None
            if d is not None and d != 0:
                amt = -abs(d)
            elif c is not None and c != 0:
                amt = abs(c)
        if not date_val or not desc_val or amt is None:
            continue
        rows.append({"date": date_val, "description": desc_val, "amount": amt})
    return rows

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
@api_router.post("/transactions/upload")
async def upload_statement(project_id: str = Form(...), file: UploadFile = File(...)):
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    content = await file.read()
    name = (file.filename or '').lower()
    rows = []
    if name.endswith('.csv') or file.content_type == 'text/csv':
        rows = parse_csv(content)
    elif name.endswith('.pdf') or file.content_type == 'application/pdf':
        rows = parse_pdf(content)
    else:
        # try CSV first
        try:
            rows = parse_csv(content)
        except Exception:
            rows = []
        if not rows:
            try:
                rows = parse_pdf(content)
            except Exception:
                pass
    if not rows:
        raise HTTPException(status_code=400, detail="Could not parse any transactions from file")

    inserted = 0
    skipped = 0
    for r in rows:
        # dedupe: same project, date, description, amount
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
    if payload.description is not None:
        update["description"] = payload.description
    if update:
        await db.transactions.update_one({"id": tx_id}, {"$set": update})

    affected_similar = 0
    if payload.apply_to_similar and payload.category_id:
        key = normalize_merchant(tx["description"])
        if key:
            # upsert rule
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
            # apply to all matching uncategorized
            all_tx = await db.transactions.find(
                {"project_id": tx["project_id"]}, {"_id": 0}
            ).to_list(10000)
            for t in all_tx:
                if normalize_merchant(t["description"]) == key and t.get("category_id") != payload.category_id:
                    await db.transactions.update_one(
                        {"id": t["id"]}, {"$set": {"category_id": payload.category_id}}
                    )
                    affected_similar += 1
    return {"ok": True, "affected_similar": affected_similar}

@api_router.delete("/transactions/{tx_id}")
async def delete_transaction(tx_id: str):
    await db.transactions.delete_one({"id": tx_id})
    return {"ok": True}

# ----- AI Suggestion -----
@api_router.post("/categorize/suggest")
async def suggest_category(payload: SuggestRequest):
    cats = await db.categories.find({"project_id": payload.project_id}, {"_id": 0}).to_list(500)
    if not cats:
        return {"suggested_category_id": None, "suggested_name": None, "reason": "No categories defined."}
    expected_type = "income" if payload.amount >= 0 else "expense"
    candidates = [c for c in cats if c.get("type") == expected_type] or cats
    cat_list = "\n".join([f"- {c['name']}" for c in candidates])

    if not EMERGENT_LLM_KEY:
        return {"suggested_category_id": None, "suggested_name": None, "reason": "LLM not configured."}

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
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"cat-{uuid.uuid4()}",
            system_message=sys_msg,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        resp = await chat.send_message(UserMessage(text=user_text))
        text = resp.strip() if isinstance(resp, str) else str(resp)
        # extract JSON
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            name = parsed.get("category_name", "").strip()
            reason = parsed.get("reason", "")
            # strip trailing parenthesized type if model added it
            clean = re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()
            for c in candidates:
                if c["name"].lower() == clean.lower() or c["name"].lower() == name.lower():
                    return {
                        "suggested_category_id": c["id"],
                        "suggested_name": c["name"],
                        "reason": reason,
                    }
        return {"suggested_category_id": None, "suggested_name": None, "reason": text[:200]}
    except Exception as e:
        logging.exception("LLM suggest failed")
        return {"suggested_category_id": None, "suggested_name": None, "reason": f"AI error: {str(e)[:120]}"}

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
    # category x month
    cat_monthly: Dict[str, List[float]] = {c["id"]: [0.0] * 12 for c in cats}
    cat_monthly["__uncategorized__"] = [0.0] * 12
    cat_yearly: Dict[str, float] = {c["id"]: 0.0 for c in cats}
    cat_yearly["__uncategorized__"] = 0.0

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
        cid = t.get("category_id") or "__uncategorized__"
        if cid not in cat_monthly:
            cat_monthly[cid] = [0.0] * 12
            cat_yearly[cid] = 0.0
        cat_monthly[cid][m] += amt
        cat_yearly[cid] += amt

    cat_breakdown = []
    for cid, total in cat_yearly.items():
        if total == 0 and not any(cat_monthly[cid]):
            continue
        if cid == "__uncategorized__":
            cat_breakdown.append({
                "category_id": None,
                "name": "Uncategorized",
                "type": "expense" if total < 0 else "income",
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

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
