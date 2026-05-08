"""AI categorization endpoints: single suggest, bulk suggest, bulk categorize, reclassify."""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from app_db import EMERGENT_LLM_KEY, db
from models import (
    BulkCategorizePayload,
    BulkSuggestPayload,
    Category,
    CategoryRule,
    SuggestRequest,
)
from services.ai import suggest_via_emergent, suggest_via_ollama
from services.helpers import force_amount_sign, normalize_merchant
from services.settings_store import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)

PALETTE = ["#364C2E", "#4B6B40", "#728A66", "#D96C4E", "#D1A77E", "#E3C8AA", "#8B5E3C", "#9E7B58"]


@router.post("/categorize/suggest")
async def suggest_category(payload: SuggestRequest):
    cats = await db.categories.find({"project_id": payload.project_id}, {"_id": 0}).to_list(500)
    if not cats:
        return {"suggested_category_id": None, "suggested_name": None, "reason": "No categories defined."}
    expected_type = "income" if payload.amount >= 0 else "expense"
    candidates = [c for c in cats if c.get("type") == expected_type] or cats
    cat_list = "\n".join([f"- {c['name']}" for c in candidates])

    settings = await get_settings()
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
            text = suggest_via_ollama(sys_msg, user_text, settings.ollama_url, settings.ollama_model)
        else:
            text = await suggest_via_emergent(sys_msg, user_text, emergent_key)
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
        logger.exception("LLM suggest failed (%s)", provider)
        msg = str(e)
        if provider == "ollama" and ("model" in msg.lower() and ("not found" in msg.lower() or "pull" in msg.lower())):
            msg = f"Ollama model '{settings.ollama_model}' not installed. Run `ollama pull {settings.ollama_model}` and try again."
        return {"suggested_category_id": None, "suggested_name": None, "reason": f"AI error: {msg[:200]}", "provider": provider}


@router.post("/transactions/bulk-suggest")
async def bulk_suggest(payload: BulkSuggestPayload):
    """Run the configured AI provider over many transactions in one go.
    Optionally creates new categories when none of the existing ones fit.
    """
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = await get_settings()
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

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in txs:
        k = normalize_merchant(t["description"]) or t["description"]
        groups.setdefault(k, []).append(t)

    created_categories: List[Dict[str, str]] = []
    cat_by_name: Dict[str, Dict[str, Any]] = {c["name"].lower(): c for c in cats}
    errors: List[str] = []
    categorized = 0

    create_hint = (
        "If none of the existing categories fit, you MAY suggest a brand new category — set is_new to true. "
        if payload.allow_create else
        "You MUST pick one of the existing categories — set is_new to false. "
    )
    sys_msg = (
        "You are a personal finance assistant. Pick the best category for each bank transaction. "
        "Prefer one of the EXISTING categories when reasonable. "
        f"{create_hint}"
        "Respond ONLY with strict JSON of the form "
        "{\"category_name\": \"<name>\", \"is_new\": <true|false>, \"type\": \"<income|expense>\", \"reason\": \"<short>\"}."
    )

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
                text = suggest_via_ollama(sys_msg, user_text, settings.ollama_url, settings.ollama_model)
            else:
                text = await suggest_via_emergent(sys_msg, user_text, emergent_key)
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
        for t in members:
            new_amt = force_amount_sign(t.get("amount", 0), cat["type"])
            await db.transactions.update_one(
                {"id": t["id"]},
                {"$set": {"category_id": cat["id"], "type": cat["type"], "amount": new_amt}},
            )
            categorized += 1
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


@router.post("/transactions/bulk-categorize")
async def bulk_categorize(payload: BulkCategorizePayload):
    if not payload.transaction_ids:
        raise HTTPException(status_code=400, detail="No transaction ids")
    target_cat = await db.categories.find_one({"id": payload.category_id}, {"_id": 0})
    if not target_cat:
        raise HTTPException(status_code=404, detail="Category not found")
    project_id = target_cat["project_id"]
    cat_type = target_cat["type"]

    txs = await db.transactions.find(
        {"id": {"$in": payload.transaction_ids}, "project_id": project_id}, {"_id": 0}
    ).to_list(10000)
    for t in txs:
        await db.transactions.update_one(
            {"id": t["id"]},
            {"$set": {
                "category_id": payload.category_id,
                "type": cat_type,
                "amount": force_amount_sign(t.get("amount", 0), cat_type),
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
                        "amount": force_amount_sign(t.get("amount", 0), cat_type),
                    }},
                )
                similar_applied += 1
    return {
        "updated": len(txs),
        "rules_added": rule_keys_added,
        "similar_applied": similar_applied,
    }


@router.post("/transactions/reclassify")
async def reclassify_transactions(project_id: str = Query(...)):
    """Repair transaction signs + types.
    - For categorized transactions: sign + type follow the assigned category's type.
    - For uncategorized: type is derived from the current amount sign.
    """
    cats = await db.categories.find({"project_id": project_id}, {"_id": 0}).to_list(500)
    cat_type_map = {c["id"]: c["type"] for c in cats}
    txs = await db.transactions.find({"project_id": project_id}, {"_id": 0}).to_list(100000)
    fixed = 0
    for t in txs:
        cur_amt = float(t.get("amount", 0))
        cid = t.get("category_id")
        update: Dict[str, Any] = {}
        if cid and cid in cat_type_map:
            target = cat_type_map[cid]
            new_amt = force_amount_sign(cur_amt, target)
            if new_amt != cur_amt:
                update["amount"] = new_amt
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
