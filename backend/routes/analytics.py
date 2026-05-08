"""Analytics endpoints: yearly summary, category drilldown, available years, recurring detector."""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter

from app_db import db
from services.helpers import normalize_merchant

router = APIRouter()


@router.get("/analytics/yearly")
async def analytics_yearly(project_id: str, year: int):
    cats = await db.categories.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    cat_map = {c["id"]: c for c in cats}
    txs = await db.transactions.find(
        {"project_id": project_id, "date": {"$regex": f"^{year:04d}"}}, {"_id": 0}
    ).to_list(50000)

    monthly_income = [0.0] * 12
    monthly_expense = [0.0] * 12
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
                "category_id": None, "name": "Uncategorized", "type": "income",
                "color": "#999999", "total": round(total, 2),
                "monthly": [round(v, 2) for v in cat_monthly[cid]],
            })
        elif cid == "__uncat_expense__":
            cat_breakdown.append({
                "category_id": None, "name": "Uncategorized", "type": "expense",
                "color": "#999999", "total": round(total, 2),
                "monthly": [round(v, 2) for v in cat_monthly[cid]],
            })
        else:
            c = cat_map.get(cid)
            if not c:
                continue
            cat_breakdown.append({
                "category_id": cid, "name": c["name"], "type": c["type"],
                "color": c.get("color", "#364C2E"), "total": round(total, 2),
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


@router.get("/analytics/category/{category_id}")
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


@router.get("/analytics/years")
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


@router.get("/analytics/recurring")
async def analytics_recurring(project_id: str, lookback_months: int = 6):
    txs = await db.transactions.find({"project_id": project_id}, {"_id": 0}).to_list(100000)
    if not txs:
        return {"recurring": [], "forecast": {"monthly_total_expense": 0.0, "monthly_total_income": 0.0}}

    cats = await db.categories.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    cat_map = {c["id"]: c for c in cats}

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
        months_seen = {it["date"][:7] for it in items}
        if len(months_seen) < 2:
            continue
        sorted_items = sorted(items, key=lambda x: x["date"])
        gaps = []
        for i in range(1, len(sorted_items)):
            d1 = datetime.strptime(sorted_items[i - 1]["date"], "%Y-%m-%d")
            d2 = datetime.strptime(sorted_items[i]["date"], "%Y-%m-%d")
            gaps.append((d2 - d1).days)
        avg_gap = sum(gaps) / len(gaps) if gaps else 30

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
        next_dt = datetime.strptime(last_seen, "%Y-%m-%d")
        next_expected = (next_dt + timedelta(days=int(round(avg_gap)))).strftime("%Y-%m-%d")

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
