"""AI categorization endpoints: single suggest, bulk suggest, bulk categorize, reclassify, split detection."""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

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


class DetectSplitsPayload(BaseModel):
    project_id: str
    min_amount: float = 25.0   # Only inspect transactions whose abs(amount) is at least this much
    max_items: int = 60        # Cost control — how many candidate transactions to ask the AI about
    only_uncategorized: bool = False


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

    # Build a quick "name -> existing category" map for resolution + a list of
    # top-level parents that the AI can hang new sub-categories under.
    cat_by_name: Dict[str, Dict[str, Any]] = {c["name"].lower(): c for c in cats}
    cat_by_id: Dict[str, Dict[str, Any]] = {c["id"]: c for c in cats}
    top_level_names = sorted({c["name"] for c in cats if not c.get("parent_id")})

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
        "When suggesting a NEW category, you MAY also suggest a parent_name to place it under (must match "
        "one of the existing TOP-LEVEL category names exactly). Setting parent_name only makes sense for "
        "new categories — leave it empty otherwise. "
        if payload.allow_create else
        "You MUST pick one of the existing categories — set is_new to false. "
    )
    sys_msg = (
        "You are a personal finance assistant. Pick the best category for each bank transaction. "
        "Prefer one of the EXISTING categories when reasonable. "
        f"{create_hint}"
        "Respond ONLY with strict JSON of the form "
        "{\"category_name\": \"<name>\", \"is_new\": <true|false>, \"type\": \"<income|expense>\", "
        "\"parent_name\": \"<optional parent>\", \"reason\": \"<short>\"}."
    )

    async def _ask_ai(desc: str, amount: float) -> Optional[Dict[str, Any]]:
        # Annotate the category list with parent names so the AI sees the tree
        # ("Petrol (under Transport)") and can suggest sub-cats correctly.
        rendered = []
        for c in cat_by_name.values():
            pid = c.get("parent_id")
            if pid and pid in cat_by_id:
                rendered.append(f"- {c['name']} ({c['type']}, under {cat_by_id[pid]['name']})")
            else:
                rendered.append(f"- {c['name']} ({c['type']})")
        existing_list = "\n".join(rendered) or "(none yet)"
        tops_str = ", ".join(top_level_names) or "(none)"
        user_text = (
            f"Transaction: {desc}\n"
            f"Amount: {amount} GBP ({'income' if amount >= 0 else 'expense'})\n\n"
            f"Existing categories (tree):\n{existing_list}\n\n"
            f"Top-level parents available to anchor a new sub-category: {tops_str}\n\n"
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
            parent_name = (parsed.get("parent_name") or "").strip()
            if not name:
                return None
            if cat_type not in ("income", "expense"):
                cat_type = "income" if amount >= 0 else "expense"
            return {"name": name, "type": cat_type, "is_new": is_new, "parent_name": parent_name, "reason": parsed.get("reason", "")}
        except Exception as e:
            errors.append(f"{desc[:40]}: {str(e)[:80]}")
            return None

    async def _resolve_category(name: str, cat_type: str, allow_new: bool, parent_name: str = "") -> Optional[Dict[str, Any]]:
        clean = re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()
        existing = cat_by_name.get(clean.lower()) or cat_by_name.get(name.lower())
        if existing:
            return existing
        if not allow_new:
            return None
        # Resolve parent (only valid for new categories) — must be a top-level
        # category of the SAME type, otherwise we silently drop the parent.
        parent_id: Optional[str] = None
        if parent_name:
            p = cat_by_name.get(parent_name.lower())
            if p and not p.get("parent_id") and p.get("type") == cat_type:
                parent_id = p["id"]
        color = PALETTE[len(cat_by_name) % len(PALETTE)]
        cat = Category(
            project_id=payload.project_id, name=clean, type=cat_type, color=color,
            parent_id=parent_id,
        )
        cdoc = cat.model_dump()
        cdoc['created_at'] = cdoc['created_at'].isoformat()
        await db.categories.insert_one(cdoc)
        created = {
            "id": cat.id, "name": cat.name, "type": cat.type, "color": cat.color,
            "project_id": payload.project_id, "parent_id": parent_id,
        }
        cat_by_name[clean.lower()] = created
        created_categories.append({
            "id": cat.id, "name": cat.name, "type": cat.type, "parent_id": parent_id,
            "parent_name": cat_by_id.get(parent_id, {}).get("name") if parent_id else None,
        })
        return created

    for key, members in groups.items():
        sample = members[0]
        suggestion = await _ask_ai(sample["description"], float(sample["amount"]))
        if not suggestion:
            continue
        cat = await _resolve_category(
            suggestion["name"], suggestion["type"], payload.allow_create,
            parent_name=suggestion.get("parent_name", ""),
        )
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



@router.post("/transactions/detect-splits")
async def detect_splits(payload: DetectSplitsPayload):
    """Use the configured AI provider to flag transactions that look like
    they might span multiple categories (e.g. a £80 supermarket charge that's
    really £50 groceries + £30 fuel).

    Returns a list of *candidate suggestions* — nothing is mutated. The
    frontend walks the user through each candidate so they confirm,
    edit, or skip individually.
    """
    proj = await db.projects.find_one({"id": payload.project_id}, {"_id": 0})
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    settings = await get_settings()
    provider = settings.ai_provider
    if provider == "none":
        raise HTTPException(status_code=400, detail="AI provider is disabled. Open Settings to enable Emergent or Ollama.")
    emergent_key = (settings.emergent_key or "").strip() or EMERGENT_LLM_KEY
    if provider == "emergent" and not emergent_key:
        raise HTTPException(status_code=400, detail="No Emergent LLM key configured.")

    cats = await db.categories.find({"project_id": payload.project_id}, {"_id": 0}).to_list(500)
    cat_by_name = {c["name"].lower(): c for c in cats}
    cat_list_str = "\n".join([f"- {c['name']} ({c['type']})" for c in cats]) or "(no categories yet)"

    q: Dict[str, Any] = {"project_id": payload.project_id}
    if payload.only_uncategorized:
        q["category_id"] = None
    raw = await db.transactions.find(q, {"_id": 0}).to_list(20000)
    # Filter out: already-split parents, split children, and tiny transactions.
    candidates = [
        t for t in raw
        if not t.get("is_split")
        and not t.get("parent_transaction_id")
        and abs(float(t.get("amount", 0))) >= payload.min_amount
    ]
    # Cap to control LLM cost.
    candidates = sorted(candidates, key=lambda t: -abs(float(t["amount"])))[: payload.max_items]
    if not candidates:
        return {"checked": 0, "candidates": []}

    sys_msg = (
        "You are a personal finance assistant. Given a bank transaction (merchant + amount), "
        "decide whether it likely covers MULTIPLE distinct spending categories. "
        "Most bank transactions cover ONE category — only mark splits when the merchant is known "
        "to mix categories (supermarkets selling fuel, hardware stores selling food, big-box retailers, "
        "etc.). Provide 2 to 4 split lines. Each line is one category from the provided list. "
        "Lines must sum exactly to the parent amount. Respond ONLY with strict JSON of the form: "
        "{\"is_split\": true|false, \"splits\": [{\"category_name\": \"...\", \"amount\": <number>, "
        "\"reason\": \"short\"}], \"reason\": \"why or why not\"}. "
        "When is_split=false return an empty splits array."
    )

    async def _ask(tx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        user_text = (
            f"Transaction: {tx['description']}\n"
            f"Amount: {tx['amount']} GBP\n\n"
            f"Available categories:\n{cat_list_str}\n\n"
            "Return JSON only. Splits MUST sum exactly to the transaction amount."
        )
        try:
            if provider == "ollama":
                text = suggest_via_ollama(sys_msg, user_text, settings.ollama_url, settings.ollama_model)
            else:
                text = await suggest_via_emergent(sys_msg, user_text, emergent_key)
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if not m:
                return None
            return json.loads(m.group(0))
        except Exception as e:
            logger.warning("split-detect failed for tx %s: %s", tx.get("id"), e)
            return None

    results: List[Dict[str, Any]] = []
    for tx in candidates:
        parsed = await _ask(tx)
        if not parsed or not parsed.get("is_split"):
            continue
        raw_splits = parsed.get("splits") or []
        # Resolve category_name -> existing category_id. Drop lines we can't match.
        resolved = []
        for s in raw_splits:
            name = (s.get("category_name") or "").strip()
            try:
                amt = float(s.get("amount"))
            except (TypeError, ValueError):
                continue
            cat = cat_by_name.get(name.lower())
            resolved.append({
                "category_id": cat["id"] if cat else None,
                "category_name": cat["name"] if cat else name,
                "category_known": bool(cat),
                "amount": round(amt, 2),
                "reason": s.get("reason", ""),
            })
        if len(resolved) < 2:
            continue
        # Validate the sum (within £0.01).
        total = sum(r["amount"] for r in resolved)
        auto_balanced = False
        if abs(total - float(tx["amount"])) > 0.01:
            # Try to re-balance the last line so we don't waste the suggestion.
            diff = round(float(tx["amount"]) - total, 2)
            resolved[-1]["amount"] = round(resolved[-1]["amount"] + diff, 2)
            total = sum(r["amount"] for r in resolved)
            if abs(total - float(tx["amount"])) > 0.01:
                continue
            auto_balanced = True
        results.append({
            "transaction": {
                "id": tx["id"], "date": tx["date"], "description": tx["description"],
                "amount": tx["amount"], "bank_account_id": tx.get("bank_account_id"),
                "category_id": tx.get("category_id"),
            },
            "splits": resolved,
            "reason": parsed.get("reason", ""),
            "auto_balanced": auto_balanced,
            "provider": provider,
        })

    return {"checked": len(candidates), "candidates": results}
