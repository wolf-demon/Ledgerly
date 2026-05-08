"""Transaction endpoints: upload, URL import, list, update, delete, export."""
import csv as csv_mod
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app_db import db
from models import (
    CategoryRule,
    Transaction,
    TransactionUpdate,
    UrlImportPayload,
)
from services.helpers import (
    apply_rules,
    force_amount_sign,
    normalize_merchant,
)
from services.parsers import google_sheet_to_csv_url, parse_any

router = APIRouter()


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


@router.post("/transactions/upload")
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
