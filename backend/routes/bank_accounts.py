"""Bank account CRUD + sort-code detection for uploads."""
import re
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app_db import db
from models import BankAccount, BankAccountCreate, BankAccountUpdate

router = APIRouter()


# UK sort code: "12-34-56" or "12 34 56" (also picks up "Sortcode:1234 56" etc.)
SORT_CODE_RE = re.compile(r"\b(?:sort\s*code\s*[:.]?\s*)?(\d{2})\s*[-\s]\s*(\d{2})\s*[-\s]\s*(\d{2})\b", re.IGNORECASE)
ACCOUNT_NUMBER_RE = re.compile(r"\b(?:account\s*(?:number|no)?\s*[:.]?\s*)?(\d{8})\b", re.IGNORECASE)


def normalise_sort_code(sc: str) -> str:
    digits = re.sub(r"\D", "", sc or "")
    if len(digits) == 6:
        return f"{digits[:2]}-{digits[2:4]}-{digits[4:]}"
    return sc or ""


def detect_from_pdf_text(text: str):
    """Pull (sort_code, account_number, inferred_bank_name) from PDF text. Any field may be None."""
    sc_match = SORT_CODE_RE.search(text)
    sort_code = None
    if sc_match:
        sort_code = f"{sc_match.group(1)}-{sc_match.group(2)}-{sc_match.group(3)}"
    acct_match = ACCOUNT_NUMBER_RE.search(text)
    account_number = acct_match.group(1) if acct_match else None
    # Guess bank name from common keywords.
    bank_name = None
    lowered = (text or "")[:4000].lower()
    KNOWN = [
        ("nationwide", "Nationwide"),
        ("bank of scotland", "Bank of Scotland"),
        ("lloyds", "Lloyds"),
        ("monzo", "Monzo"),
        ("starling", "Starling"),
        ("barclays", "Barclays"),
        ("hsbc", "HSBC"),
        ("santander", "Santander"),
        ("natwest", "NatWest"),
        ("first direct", "First Direct"),
        ("revolut", "Revolut"),
        ("halifax", "Halifax"),
    ]
    for needle, name in KNOWN:
        if needle in lowered:
            bank_name = name
            break
    return sort_code, account_number, bank_name


def _doc_to_model(doc):
    if isinstance(doc.get("created_at"), str):
        doc["created_at"] = datetime.fromisoformat(doc["created_at"])
    return doc


@router.get("/bank-accounts", response_model=List[BankAccount])
async def list_bank_accounts(project_id: str):
    docs = await db.bank_accounts.find({"project_id": project_id}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return [_doc_to_model(d) for d in docs]


@router.post("/bank-accounts", response_model=BankAccount)
async def create_bank_account(payload: BankAccountCreate):
    if payload.sort_code:
        payload.sort_code = normalise_sort_code(payload.sort_code)
    if payload.sort_code:
        # Reject duplicates per project (same sort code + account number).
        existing = await db.bank_accounts.find_one({
            "project_id": payload.project_id,
            "sort_code": payload.sort_code,
            "account_number": payload.account_number,
        }, {"_id": 0})
        if existing:
            raise HTTPException(status_code=409, detail=f"An account with this sort code already exists: {existing['name']}")
    acct = BankAccount(**payload.model_dump())
    doc = acct.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.bank_accounts.insert_one(doc)
    return acct


@router.put("/bank-accounts/{account_id}", response_model=BankAccount)
async def update_bank_account(account_id: str, payload: BankAccountUpdate):
    update = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "sort_code" in update:
        update["sort_code"] = normalise_sort_code(update["sort_code"])
    if update:
        await db.bank_accounts.update_one({"id": account_id}, {"$set": update})
    doc = await db.bank_accounts.find_one({"id": account_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Bank account not found")
    return _doc_to_model(doc)


@router.delete("/bank-accounts/{account_id}")
async def delete_bank_account(account_id: str):
    """Delete a bank account. Transactions are kept but un-linked (bank_account_id -> NULL)."""
    await db.bank_accounts.delete_one({"id": account_id})
    await db.transactions.update_many({"bank_account_id": account_id}, {"$set": {"bank_account_id": None}})
    return {"ok": True}


class ReassignPayload(BaseModel):
    target_id: str


@router.put("/bank-accounts/{account_id}/reassign")
async def reassign_bank_account(account_id: str, payload: ReassignPayload):
    """Move every transaction currently linked to `account_id` over to
    `payload.target_id` and delete the (now-empty) source account.

    Used by the Upload page when the user wants to override the auto-detected
    bank account: a fresh account was just auto-created from the PDF — the
    user picks an existing one in the dropdown — we move the rows there and
    drop the duplicate.
    """
    src = await db.bank_accounts.find_one({"id": account_id}, {"_id": 0})
    target = await db.bank_accounts.find_one({"id": payload.target_id}, {"_id": 0})
    if not src or not target:
        raise HTTPException(status_code=404, detail="Source or target account not found")
    if src["project_id"] != target["project_id"]:
        raise HTTPException(status_code=400, detail="Source and target must belong to the same project")
    if src["id"] == target["id"]:
        return {"ok": True, "moved": 0}

    # Reassign every transaction on the source account to the target account.
    txs = await db.transactions.find({"bank_account_id": account_id}, {"_id": 0}).to_list(100000)
    for t in txs:
        await db.transactions.update_one({"id": t["id"]}, {"$set": {"bank_account_id": payload.target_id}})

    # Drop the now-empty source account so the picker doesn't accumulate junk.
    await db.bank_accounts.delete_one({"id": account_id})
    return {"ok": True, "moved": len(txs)}
