"""Iteration 12 — Split transactions backend tests.

Covers:
(a) happy path split + parent flagged is_split=true
(b) validation: sign mismatch, sum mismatch, <2 lines, already-split, child split
(c) include_split_parents filter on /transactions
(d) GET /transactions/{id}/splits returns the children
(e) DELETE /transactions/{id}/split unsplits — children deleted, flag cleared
(f) analytics/yearly + budgets/progress exclude is_split=true parents
(g) detect-splits endpoint — 400 cleanly when AI provider is 'none'
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
FIXTURES = Path(__file__).parent / "fixtures"


# ── helpers ────────────────────────────────────────────────────────────────


def _make_project(name_prefix: str) -> Dict:
    r = requests.post(
        f"{API}/projects",
        json={"name": f"TEST_{name_prefix}_{int(datetime.utcnow().timestamp() * 1000)}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _delete_project(pid: str) -> None:
    try:
        requests.delete(f"{API}/projects/{pid}", timeout=15)
    except Exception:
        pass


def _upload_csv(project_id: str, rows: List[tuple]) -> Dict:
    """rows: list of (date, description, amount). Uploads via CSV."""
    lines = ["Date,Description,Amount"]
    for d, desc, amt in rows:
        lines.append(f"{d},{desc},{amt}")
    csv_bytes = ("\n".join(lines) + "\n").encode()
    r = requests.post(
        f"{API}/transactions/upload",
        files={"file": ("seed.csv", csv_bytes, "text/csv")},
        data={"project_id": project_id},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _get_txs(project_id: str, **params) -> List[Dict]:
    p = {"project_id": project_id, **params}
    r = requests.get(f"{API}/transactions", params=p, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


# ── (a) Happy path ─────────────────────────────────────────────────────────


class TestSplitHappyPath:
    @pytest.fixture(scope="class")
    def ctx(self):
        p = _make_project("Iter12_Happy")
        pid = p["id"]
        _upload_csv(pid, [("2026-03-10", "TEST_TESCO_BIG", -80.00)])
        cat_g = requests.post(f"{API}/categories", json={
            "project_id": pid, "name": "TEST_Groceries", "type": "expense"}, timeout=15).json()
        cat_f = requests.post(f"{API}/categories", json={
            "project_id": pid, "name": "TEST_Fuel", "type": "expense"}, timeout=15).json()
        yield {"pid": pid, "cat_g": cat_g, "cat_f": cat_f}
        _delete_project(pid)

    def test_split_creates_children_and_flags_parent(self, ctx):
        pid = ctx["pid"]
        txs = _get_txs(pid)
        parent = next(t for t in txs if t["description"] == "TEST_TESCO_BIG")
        r = requests.post(f"{API}/transactions/{parent['id']}/split", json={
            "splits": [
                {"amount": -50.00, "category_id": ctx["cat_g"]["id"], "description": "Groceries"},
                {"amount": -30.00, "category_id": ctx["cat_f"]["id"], "description": "Fuel"},
            ]
        }, timeout=15)
        assert r.status_code == 200, r.text
        children = r.json()
        assert len(children) == 2
        assert all(c["parent_transaction_id"] == parent["id"] for c in children)
        assert {round(c["amount"], 2) for c in children} == {-50.00, -30.00}

        # default listing must hide the parent
        default_list = _get_txs(pid)
        assert not any(t["id"] == parent["id"] for t in default_list), "parent should be hidden"
        assert sum(1 for t in default_list if t.get("parent_transaction_id") == parent["id"]) == 2

        # include_split_parents=true brings it back AND it must have is_split=True
        with_parents = _get_txs(pid, include_split_parents=True)
        parent_row = next(t for t in with_parents if t["id"] == parent["id"])
        assert parent_row["is_split"] is True

    def test_list_splits_endpoint(self, ctx):
        pid = ctx["pid"]
        txs = _get_txs(pid, include_split_parents=True)
        parent = next(t for t in txs if t["description"] == "TEST_TESCO_BIG")
        r = requests.get(f"{API}/transactions/{parent['id']}/splits", timeout=15)
        assert r.status_code == 200, r.text
        kids = r.json()
        assert len(kids) == 2
        assert all(k["parent_transaction_id"] == parent["id"] for k in kids)

    def test_unsplit_clears_children_and_flag(self, ctx):
        pid = ctx["pid"]
        txs = _get_txs(pid, include_split_parents=True)
        parent = next(t for t in txs if t["description"] == "TEST_TESCO_BIG")
        r = requests.delete(f"{API}/transactions/{parent['id']}/split", timeout=15)
        assert r.status_code == 200, r.text

        # No more children
        kids = requests.get(f"{API}/transactions/{parent['id']}/splits", timeout=15).json()
        assert kids == []

        # Parent visible in default listing now (is_split=False)
        default_list = _get_txs(pid)
        prow = next(t for t in default_list if t["id"] == parent["id"])
        assert prow["is_split"] is False


# ── (b) Validation errors ──────────────────────────────────────────────────


class TestSplitValidation:
    @pytest.fixture(scope="class")
    def ctx(self):
        p = _make_project("Iter12_Validation")
        pid = p["id"]
        _upload_csv(pid, [
            ("2026-03-11", "TEST_VAL_TX", -100.00),
            ("2026-03-12", "TEST_VAL_TX2", -60.00),
        ])
        cat = requests.post(f"{API}/categories", json={
            "project_id": pid, "name": "TEST_Cat_V", "type": "expense"}, timeout=15).json()
        yield {"pid": pid, "cat": cat}
        _delete_project(pid)

    def _parent(self, pid, desc):
        return next(t for t in _get_txs(pid) if t["description"] == desc)

    def test_sum_mismatch(self, ctx):
        tx = self._parent(ctx["pid"], "TEST_VAL_TX")
        r = requests.post(f"{API}/transactions/{tx['id']}/split", json={
            "splits": [
                {"amount": -50.00, "category_id": ctx["cat"]["id"]},
                {"amount": -40.00, "category_id": ctx["cat"]["id"]},
            ]
        }, timeout=15)
        assert r.status_code == 400, r.text
        assert "delta" in r.json()["detail"].lower() or "total" in r.json()["detail"].lower()

    def test_sign_mismatch(self, ctx):
        tx = self._parent(ctx["pid"], "TEST_VAL_TX")
        r = requests.post(f"{API}/transactions/{tx['id']}/split", json={
            "splits": [
                {"amount": -120.00, "category_id": ctx["cat"]["id"]},
                {"amount":   20.00, "category_id": ctx["cat"]["id"]},  # wrong sign
            ]
        }, timeout=15)
        assert r.status_code == 400, r.text
        assert "sign" in r.json()["detail"].lower()

    def test_fewer_than_two_lines(self, ctx):
        tx = self._parent(ctx["pid"], "TEST_VAL_TX")
        r = requests.post(f"{API}/transactions/{tx['id']}/split", json={
            "splits": [{"amount": -100.00, "category_id": ctx["cat"]["id"]}]
        }, timeout=15)
        assert r.status_code == 400, r.text
        assert "2" in r.json()["detail"] or "at least" in r.json()["detail"].lower()

    def test_cannot_resplit_or_split_child(self, ctx):
        # First, successfully split TEST_VAL_TX2
        tx = self._parent(ctx["pid"], "TEST_VAL_TX2")
        ok = requests.post(f"{API}/transactions/{tx['id']}/split", json={
            "splits": [
                {"amount": -30.00, "category_id": ctx["cat"]["id"]},
                {"amount": -30.00, "category_id": ctx["cat"]["id"]},
            ]
        }, timeout=15)
        assert ok.status_code == 200, ok.text
        child = ok.json()[0]

        # Re-split the parent → 400 already split
        re = requests.post(f"{API}/transactions/{tx['id']}/split", json={
            "splits": [
                {"amount": -30.00, "category_id": ctx["cat"]["id"]},
                {"amount": -30.00, "category_id": ctx["cat"]["id"]},
            ]
        }, timeout=15)
        assert re.status_code == 400, re.text
        assert "already" in re.json()["detail"].lower()

        # Split a child row → 400 cannot split a child
        ch = requests.post(f"{API}/transactions/{child['id']}/split", json={
            "splits": [
                {"amount": -15.00, "category_id": ctx["cat"]["id"]},
                {"amount": -15.00, "category_id": ctx["cat"]["id"]},
            ]
        }, timeout=15)
        assert ch.status_code == 400, ch.text
        assert "child" in ch.json()["detail"].lower()


# ── (c) Analytics + budgets exclude split parents ──────────────────────────


class TestAnalyticsBudgetsExcludeSplitParents:
    @pytest.fixture(scope="class")
    def ctx(self):
        p = _make_project("Iter12_Analytics")
        pid = p["id"]
        _upload_csv(pid, [("2026-03-15", "TEST_BIG_SHOP", -200.00)])
        cat_a = requests.post(f"{API}/categories", json={
            "project_id": pid, "name": "TEST_A", "type": "expense"}, timeout=15).json()
        cat_b = requests.post(f"{API}/categories", json={
            "project_id": pid, "name": "TEST_B", "type": "expense"}, timeout=15).json()
        # £500/mo budget on cat_a
        requests.post(f"{API}/budgets", json={
            "project_id": pid, "category_id": cat_a["id"], "period": "monthly", "amount": 500.0,
        }, timeout=15)
        yield {"pid": pid, "cat_a": cat_a, "cat_b": cat_b}
        _delete_project(pid)

    def test_yearly_total_unchanged_after_split(self, ctx):
        pid = ctx["pid"]
        y0 = requests.get(f"{API}/analytics/yearly", params={"project_id": pid, "year": 2026}, timeout=15).json()
        base_expense = y0["total_expense"]
        assert abs(base_expense - 200.0) < 0.01, y0

        # Split the £200 into £120 (cat_a) + £80 (cat_b)
        parent = next(t for t in _get_txs(pid) if t["description"] == "TEST_BIG_SHOP")
        r = requests.post(f"{API}/transactions/{parent['id']}/split", json={
            "splits": [
                {"amount": -120.00, "category_id": ctx["cat_a"]["id"]},
                {"amount":  -80.00, "category_id": ctx["cat_b"]["id"]},
            ]
        }, timeout=15)
        assert r.status_code == 200, r.text

        y1 = requests.get(f"{API}/analytics/yearly", params={"project_id": pid, "year": 2026}, timeout=15).json()
        assert abs(y1["total_expense"] - 200.0) < 0.01, y1  # unchanged net
        # Category breakdown: cat_a 120, cat_b 80, no Uncategorized expense remaining
        by_id = {c["category_id"]: c for c in y1["categories"]}
        assert abs(by_id[ctx["cat_a"]["id"]]["total"] + 120.0) < 0.01
        assert abs(by_id[ctx["cat_b"]["id"]]["total"] + 80.0) < 0.01

    def test_budgets_progress_uses_child_spend(self, ctx):
        pid = ctx["pid"]
        prog = requests.get(f"{API}/budgets/progress", params={
            "project_id": pid, "year": 2026, "month": 3,
        }, timeout=15).json()
        row = next(i for i in prog["items"] if i["category_id"] == ctx["cat_a"]["id"])
        # Only the child (£120) should contribute — NOT the parent £200.
        assert abs(row["spent"] - 120.0) < 0.01, row


# ── (d) detect-splits endpoint requires AI ─────────────────────────────────


class TestDetectSplitsEndpoint:
    def test_returns_400_when_ai_disabled(self):
        # Read current settings; if provider != none, this might pass with a real run.
        s = requests.get(f"{API}/settings", timeout=15).json()
        provider = s.get("ai_provider", "none")
        p = _make_project("Iter12_Detect")
        pid = p["id"]
        try:
            payload = {"project_id": pid, "min_amount": 25.0, "max_items": 10}
            r = requests.post(f"{API}/transactions/detect-splits", json=payload, timeout=30)
            if provider == "none":
                assert r.status_code == 400, r.text
                assert "disabled" in r.json()["detail"].lower() or "ai" in r.json()["detail"].lower()
            else:
                # With AI enabled and no candidates, should return checked=0 candidates=[]
                assert r.status_code in (200, 400), r.text
        finally:
            _delete_project(pid)
