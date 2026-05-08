"""Budget endpoints + progress (spent vs budgeted) calculator with monthly rollover."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException

from app_db import db
from models import Budget, BudgetUpsert

router = APIRouter()


def _isoformat_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(doc.get("created_at"), str):
        doc["created_at"] = datetime.fromisoformat(doc["created_at"])
    # SQLite stores rollover as 0/1 INTEGER — coerce back to bool for the API
    if "rollover" in doc:
        doc["rollover"] = bool(doc["rollover"])
    return doc


@router.get("/budgets", response_model=List[Budget])
async def list_budgets(project_id: str):
    docs = await db.budgets.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
    return [_isoformat_doc(d) for d in docs]


@router.post("/budgets", response_model=Budget)
async def upsert_budget(payload: BudgetUpsert):
    """Create or update a budget for (project_id, category_id, period).
    Setting amount=0 deletes the budget. Same category can have one monthly + one yearly budget.
    """
    if payload.period not in ("monthly", "yearly"):
        raise HTTPException(status_code=400, detail="period must be 'monthly' or 'yearly'")
    if payload.amount < 0:
        raise HTTPException(status_code=400, detail="amount must be >= 0")
    cat = await db.categories.find_one({"id": payload.category_id, "project_id": payload.project_id}, {"_id": 0})
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found in this project")

    spec = {
        "project_id": payload.project_id,
        "category_id": payload.category_id,
        "period": payload.period,
    }
    existing = await db.budgets.find_one(spec, {"_id": 0})

    if payload.amount == 0:
        if existing:
            await db.budgets.delete_one({"id": existing["id"]})
        # Return a synthetic 0-amount budget so the frontend has consistent shape
        synthetic = Budget(
            project_id=payload.project_id,
            category_id=payload.category_id,
            period=payload.period,
            amount=0,
            rollover=payload.rollover,
        )
        return synthetic

    if existing:
        await db.budgets.update_one(
            {"id": existing["id"]},
            {"$set": {"amount": float(payload.amount), "rollover": 1 if payload.rollover else 0}},
        )
        existing["amount"] = float(payload.amount)
        existing["rollover"] = payload.rollover
        return _isoformat_doc(existing)

    budget = Budget(**payload.model_dump())
    doc = budget.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["rollover"] = 1 if doc["rollover"] else 0
    await db.budgets.insert_one(doc)
    return budget


@router.delete("/budgets/{budget_id}")
async def delete_budget(budget_id: str):
    await db.budgets.delete_one({"id": budget_id})
    return {"ok": True}


def _signed_spent(amount: float, cat_type: str) -> float:
    """Return the absolute amount spent / received against a budget for this transaction.

    For an expense category we count |amount| of any negative tx (an income-shaped
    refund inside an expense category reduces the spent figure, mirroring real
    bank behaviour). For an income category we count positive tx values toward
    the target. Mixed-sign noise is handled by simply summing the signed amount
    and clamping at zero on the frontend if needed.
    """
    if cat_type == "expense":
        return -amount  # expenses are negative — flipping makes them positive
    return amount


def _prev_month(year: int, month: int) -> tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


@router.get("/budgets/progress")
async def budgets_progress(project_id: str, year: int, month: Optional[int] = None):
    """Compute spent vs budgeted for every category that has a budget.

    - If `month` is given: monthly budgets evaluated for that (year, month) with
      optional rollover (carried-over leftover from prior consecutive months
      whose `rollover=true`); yearly budgets evaluated YTD (year-to-month).
    - If `month` is None: monthly budgets are evaluated as the *latest* month
      with any tx in this project (or the current month); yearly budgets cover
      the whole year.
    """
    cats = await db.categories.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    cat_map = {c["id"]: c for c in cats}
    budgets = await db.budgets.find({"project_id": project_id}, {"_id": 0}).to_list(2000)
    if not budgets:
        return {"year": year, "month": month, "items": []}

    # If month is None, default to current month or latest month with data.
    if month is None:
        month = datetime.now().month

    # Pull this year's transactions once and bucket by month + category.
    txs = await db.transactions.find(
        {"project_id": project_id, "date": {"$regex": f"^{year:04d}"}}, {"_id": 0}
    ).to_list(100000)
    # spent[(category_id, ym)] = absolute spend for that category that month.
    spent_by_cat_month: Dict[tuple, float] = {}
    yearly_spent: Dict[str, float] = {}
    for t in txs:
        cid = t.get("category_id")
        if not cid or cid not in cat_map:
            continue
        try:
            m = int(t["date"][5:7])
        except Exception:
            continue
        cat_type = cat_map[cid]["type"]
        signed = _signed_spent(float(t["amount"]), cat_type)
        spent_by_cat_month[(cid, m)] = spent_by_cat_month.get((cid, m), 0) + signed
        # Yearly: only count months up to and including the requested month
        if m <= month:
            yearly_spent[cid] = yearly_spent.get(cid, 0) + signed

    # Prior-year tx (only needed for monthly rollover that crosses Jan boundary).
    # We walk back at most 11 months, so peek at last year if needed.
    needs_prev_year = any(b["rollover"] and b["period"] == "monthly" for b in budgets) and month <= 11
    prev_year_spent: Dict[tuple, float] = {}
    if needs_prev_year:
        ptxs = await db.transactions.find(
            {"project_id": project_id, "date": {"$regex": f"^{year - 1:04d}"}}, {"_id": 0}
        ).to_list(100000)
        for t in ptxs:
            cid = t.get("category_id")
            if not cid or cid not in cat_map:
                continue
            try:
                m = int(t["date"][5:7])
            except Exception:
                continue
            cat_type = cat_map[cid]["type"]
            signed = _signed_spent(float(t["amount"]), cat_type)
            prev_year_spent[(cid, m)] = prev_year_spent.get((cid, m), 0) + signed

    def _spent_for(cid: str, y: int, m: int) -> float:
        if y == year:
            return spent_by_cat_month.get((cid, m), 0.0)
        if y == year - 1:
            return prev_year_spent.get((cid, m), 0.0)
        return 0.0

    items: List[Dict[str, Any]] = []
    for b in budgets:
        cid = b["category_id"]
        cat = cat_map.get(cid)
        if not cat:
            continue
        period = b["period"]
        base_amount = float(b["amount"])
        rollover = bool(b.get("rollover"))

        if period == "yearly":
            spent = yearly_spent.get(cid, 0.0)
            effective = base_amount
        else:
            spent = spent_by_cat_month.get((cid, month), 0.0)
            effective = base_amount
            if rollover:
                # Walk backwards while the budget is rollover-enabled, accumulate leftover.
                cy, cm = _prev_month(year, month)
                # Hard-cap to 11 months of look-back to avoid runaway loops.
                steps = 0
                while steps < 11:
                    prior_spent = _spent_for(cid, cy, cm)
                    leftover = max(0.0, base_amount - prior_spent)
                    if leftover == 0:
                        break
                    effective += leftover
                    cy, cm = _prev_month(cy, cm)
                    steps += 1

        remaining = effective - spent
        percent = (spent / effective * 100) if effective > 0 else 0.0
        if percent >= 100:
            status = "over"
        elif percent >= 80:
            status = "warn"
        else:
            status = "ok"

        items.append({
            "id": b["id"],
            "category_id": cid,
            "category_name": cat["name"],
            "category_color": cat.get("color", "#364C2E"),
            "category_type": cat["type"],
            "period": period,
            "amount": round(base_amount, 2),
            "effective_amount": round(effective, 2),
            "spent": round(spent, 2),
            "remaining": round(remaining, 2),
            "percent": round(percent, 1),
            "status": status,
            "rollover": rollover,
        })

    # Stable sort: over-budget first, then warn, then ok; within each by % desc.
    status_order = {"over": 0, "warn": 1, "ok": 2}
    items.sort(key=lambda x: (status_order.get(x["status"], 3), -x["percent"]))

    return {"year": year, "month": month, "items": items}
