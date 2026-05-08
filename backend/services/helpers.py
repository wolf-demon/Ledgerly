"""Shared helpers: amount/date parsing, merchant normalization, sign-flipping, rule application."""
import re
from typing import Any, List, Optional

import pandas as pd

from app_db import db


def normalize_merchant(description: str) -> str:
    """Normalize merchant description for rule matching."""
    s = description.upper()
    s = re.sub(r'\d{2}[/\-]\d{2}[/\-]\d{2,4}', '', s)
    s = re.sub(r'\b\d{4,}\b', '', s)
    s = re.sub(r'[^A-Z &]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
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


def force_amount_sign(amount: float, cat_type: Optional[str]) -> float:
    """Force a transaction amount to match a category's type.

    expense -> negative, income -> positive. Returns the (possibly flipped) amount.
    If `cat_type` is None or unrecognized the amount is returned as-is.
    """
    try:
        cur = float(amount)
    except (TypeError, ValueError):
        return amount
    if cat_type == "expense" and cur > 0:
        return -abs(cur)
    if cat_type == "income" and cur < 0:
        return abs(cur)
    return cur


async def apply_rules(project_id: str, description: str) -> Optional[str]:
    """Look up an existing merchant->category rule for this description."""
    key = normalize_merchant(description)
    if not key:
        return None
    rule = await db.rules.find_one({"project_id": project_id, "pattern": key}, {"_id": 0})
    if rule:
        return rule.get("category_id")
    return None
