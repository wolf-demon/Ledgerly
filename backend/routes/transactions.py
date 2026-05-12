"""Transaction endpoints: upload, URL import, list, update, delete, export."""
import csv as csv_mod
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app_db import db
from models import (
    BankAccount,
    CategoryRule,
    Transaction,
    TransactionUpdate,
    UrlImportPayload,
)
from routes.bank_accounts import detect_from_pdf_text, normalise_sort_code
from services.helpers import (
    apply_rules,
    force_amount_sign,
    normalize_merchant,
)
from services.parsers import google_sheet_to_csv_url, parse_any

router = APIRouter()


async def _resolve_bank_account(
    project_id: str, raw_content: bytes, filename: str, explicit_id: Optional[str]
) -> tuple[Optional[str], Dict[str, Any]]:
    """Pick (or auto-create) a bank account for this upload.

    Returns (bank_account_id, info_dict_for_response). The info dict reports
    whether the account was auto-detected, newly created, or unknown.
    """
    info: Dict[str, Any] = {"auto_detected": False, "created": False, "sort_code": None}

    # 1. Explicit override from the upload form always wins.
    if explicit_id:
        acct = await db.bank_accounts.find_one({"id": explicit_id, "project_id": project_id}, {"_id": 0})
        if acct:
            info["account_name"] = acct["name"]
            return explicit_id, info

    # 2. PDF-only auto-detect via sort code embedded in the file text.
    if not filename.lower().endswith(".pdf"):
        return None, info
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(raw_content)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages[:2])  # first 2 pages
    except Exception:
        return None, info

    sort_code, account_number, bank_name = detect_from_pdf_text(text)
    if not sort_code:
        return None, info
    info["sort_code"] = sort_code

    # 3. Match an existing account in this project.
    match = await db.bank_accounts.find_one(
        {"project_id": project_id, "sort_code": sort_code}, {"_id": 0}
    )
    if match:
        info["auto_detected"] = True
        info["account_name"] = match["name"]
        return match["id"], info

    # 4. None matched → auto-create with the detected metadata.
    new_name = bank_name or f"Account •••{(account_number or '')[-4:]}" or "Detected account"
    palette = ["#728A66", "#4B6B40", "#D96C4E", "#D1A77E", "#8B5E3C"]
    existing_count = len(await db.bank_accounts.find({"project_id": project_id}, {"_id": 0}).to_list(200))
    acct = BankAccount(
        project_id=project_id,
        name=new_name,
        sort_code=normalise_sort_code(sort_code),
        account_number=account_number,
        color=palette[existing_count % len(palette)],
    )
    doc = acct.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.bank_accounts.insert_one(doc)
    info["auto_detected"] = True
    info["created"] = True
    info["account_name"] = new_name
    return acct.id, info


async def _next_time_for_date(project_id: str, bank_account_id: Optional[str], date: str) -> str:
    """Compute a sequential HH:MM:SS for a same-date import so duplicates / order
    is preserved. We bucket per (project, bank_account, date) and increment by
    one second from the latest existing time on that date.
    """
    spec: Dict[str, Any] = {"project_id": project_id, "date": date}
    if bank_account_id:
        spec["bank_account_id"] = bank_account_id
    existing = await db.transactions.find(spec, {"_id": 0}).to_list(10000)
    max_seconds = 0
    for t in existing:
        tm = t.get("time")
        if not tm:
            continue
        parts = tm.split(":")
        if len(parts) >= 2:
            try:
                h, m, s = int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0
                max_seconds = max(max_seconds, h * 3600 + m * 60 + s)
            except ValueError:
                continue
    next_seconds = max_seconds + 1
    h, rem = divmod(next_seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 23:
        h, m, s = 23, 59, 59  # cap; unusual to have >23h of dupes
    return f"{h:02d}:{m:02d}:{s:02d}"


async def _ingest_rows(
    project_id: str, rows: List[Dict[str, Any]], bank_account_id: Optional[str] = None
) -> Dict[str, int]:
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
        time_str = r.get("time") or await _next_time_for_date(project_id, bank_account_id, r["date"])
        tx = Transaction(
            project_id=project_id,
            bank_account_id=bank_account_id,
            date=r["date"],
            time=time_str,
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


@router.post("/transactions/upload")
async def upload_statement(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    bank_account_id: Optional[str] = Form(None),
):
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

    bank_id, bank_info = await _resolve_bank_account(project_id, content, file.filename or "", bank_account_id)
    result = await _ingest_rows(project_id, rows, bank_account_id=bank_id)
    result["bank_account"] = bank_info
    if bank_id:
        result["bank_account_id"] = bank_id
    return result


@router.post("/transactions/import-url")
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
    if is_gsheet:
        filename_hint = "google-sheet.csv"
        ct_hint = "text/csv"
    else:
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


@router.get("/transactions", response_model=List[Transaction])
async def list_transactions(
    project_id: str,
    year: Optional[int] = None,
    month: Optional[int] = None,
    uncategorized: Optional[bool] = None,
    bank_account_id: Optional[str] = None,
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
    if bank_account_id:
        q["bank_account_id"] = bank_account_id
    docs = await db.transactions.find(q, {"_id": 0}).sort("date", -1).to_list(limit)
    for d in docs:
        if isinstance(d.get('created_at'), str):
            d['created_at'] = datetime.fromisoformat(d['created_at'])
    return docs


@router.put("/transactions/{tx_id}")
async def update_transaction(tx_id: str, payload: TransactionUpdate):
    tx = await db.transactions.find_one({"id": tx_id}, {"_id": 0})
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    update: Dict[str, Any] = {}
    if payload.category_id is not None:
        update["category_id"] = payload.category_id
        cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
        if cat:
            update["type"] = cat["type"]
            update["amount"] = force_amount_sign(tx.get("amount", 0), cat["type"])
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
                        sub_update["amount"] = force_amount_sign(t.get("amount", 0), cat_type)
                    await db.transactions.update_one({"id": t["id"]}, {"$set": sub_update})
                    affected_similar += 1
    return {"ok": True, "affected_similar": affected_similar}


@router.delete("/transactions/{tx_id}")
async def delete_transaction(tx_id: str):
    await db.transactions.delete_one({"id": tx_id})
    return {"ok": True}


@router.get("/transactions/export")
async def export_transactions_csv(project_id: str, year: Optional[int] = None):
    q: Dict[str, Any] = {"project_id": project_id}
    if year is not None:
        q["date"] = {"$regex": f"^{year:04d}"}
    txs = await db.transactions.find(q, {"_id": 0}).sort("date", 1).to_list(100000)
    cats = await db.categories.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    cat_map = {c["id"]: c["name"] for c in cats}
    proj = await db.projects.find_one({"id": project_id}, {"_id": 0})
    proj_name = (proj or {}).get("name", "project").replace(" ", "_")

    buf = io.StringIO()
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
