"""Iteration 11 — bank accounts CRUD/auto-detect + sub-categories + budget roll-up.

Hits the live REACT_APP_BACKEND_URL like the rest of the suite. Each test class
creates its own throw-away project and deletes it on teardown (which now also
cascades into bank_accounts).
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Dict

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
FIXTURES = Path(__file__).parent / "fixtures"


# ─── helpers ────────────────────────────────────────────────────────────────


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


def _upload_pdf(project_id: str, fixture: str):
    with open(FIXTURES / fixture, "rb") as fh:
        files = {"file": (fixture, fh, "application/pdf")}
        data = {"project_id": project_id}
        r = requests.post(f"{API}/transactions/upload", files=files, data=data, timeout=120)
    assert r.status_code == 200, r.text
    return r.json()


# ─── (a) Bank account CRUD + 409 on duplicate ───────────────────────────────


class TestBankAccountsCRUD:
    @pytest.fixture(scope="class")
    def project(self):
        p = _make_project("Iter11_BankCRUD")
        yield p
        _delete_project(p["id"])

    def test_create_then_list(self, project):
        r = requests.post(f"{API}/bank-accounts", json={
            "project_id": project["id"],
            "name": "TEST Current",
            "sort_code": "11-22-33",
            "account_number": "12345678",
        }, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "TEST Current"
        assert body["sort_code"] == "11-22-33"
        assert body["project_id"] == project["id"]
        assert "id" in body

        lr = requests.get(f"{API}/bank-accounts", params={"project_id": project["id"]}, timeout=15)
        assert lr.status_code == 200
        assert any(a["id"] == body["id"] for a in lr.json())

    def test_duplicate_returns_409(self, project):
        # Same sort_code + account_number must conflict.
        r = requests.post(f"{API}/bank-accounts", json={
            "project_id": project["id"],
            "name": "Dup",
            "sort_code": "11-22-33",
            "account_number": "12345678",
        }, timeout=15)
        assert r.status_code == 409, r.text

    def test_update_name_color_sort_code(self, project):
        # Find the account from the first test.
        accts = requests.get(f"{API}/bank-accounts", params={"project_id": project["id"]}, timeout=15).json()
        acct = next(a for a in accts if a["sort_code"] == "11-22-33")
        r = requests.put(f"{API}/bank-accounts/{acct['id']}", json={
            "name": "Renamed",
            "color": "#123456",
            "sort_code": "44-55-66",
        }, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "Renamed"
        assert body["color"] == "#123456"
        assert body["sort_code"] == "44-55-66"

    def test_delete_detaches_transactions(self, project):
        # Create a fresh acct, attach a tx, then delete the acct.
        a = requests.post(f"{API}/bank-accounts", json={
            "project_id": project["id"], "name": "ToDelete", "sort_code": "99-99-99", "account_number": "00000001",
        }, timeout=15).json()

        # Insert via upload by attaching this account explicitly.
        with open(FIXTURES / "nationwide_mar2026.pdf", "rb") as fh:
            r = requests.post(
                f"{API}/transactions/upload",
                files={"file": ("nationwide_mar2026.pdf", fh, "application/pdf")},
                data={"project_id": project["id"], "bank_account_id": a["id"]},
                timeout=120,
            )
        assert r.status_code == 200, r.text

        # Confirm we have at least one tx on this account.
        txs = requests.get(f"{API}/transactions", params={
            "project_id": project["id"], "bank_account_id": a["id"],
        }, timeout=15).json()
        assert len(txs) > 0

        # Delete the account.
        d = requests.delete(f"{API}/bank-accounts/{a['id']}", timeout=15)
        assert d.status_code == 200

        # The transactions should still exist but be detached.
        all_tx = requests.get(f"{API}/transactions", params={"project_id": project["id"]}, timeout=15).json()
        for t in all_tx:
            assert t.get("bank_account_id") != a["id"]


# ─── (b) PDF auto-detect ────────────────────────────────────────────────────


class TestPdfAutoDetect:
    @pytest.fixture(scope="class")
    def project(self):
        p = _make_project("Iter11_AutoDetect")
        yield p
        _delete_project(p["id"])

    def test_nationwide_auto_create(self, project):
        body = _upload_pdf(project["id"], "nationwide_mar2026.pdf")
        info = body["bank_account"]
        assert info["auto_detected"] is True, body
        assert info["created"] is True, body
        assert info["sort_code"] == "07-19-86", body
        assert info["account_name"] == "Nationwide", body

    def test_bos_auto_create(self, project):
        body = _upload_pdf(project["id"], "bos_jan2026.pdf")
        info = body["bank_account"]
        assert info["auto_detected"] is True, body
        assert info["created"] is True, body
        assert info["sort_code"] == "80-46-95", body
        assert info["account_name"] == "Bank of Scotland", body

    def test_nationwide_reupload_reuses_account(self, project):
        body = _upload_pdf(project["id"], "nationwide_mar2026.pdf")
        info = body["bank_account"]
        assert info["auto_detected"] is True, body
        assert info["created"] is False, body
        assert info["account_name"] == "Nationwide", body

    def test_transactions_have_time_and_sequential(self, project):
        # Find the Nationwide account & inspect its tx times.
        accts = requests.get(f"{API}/bank-accounts", params={"project_id": project["id"]}, timeout=15).json()
        nationwide = next(a for a in accts if a["name"] == "Nationwide")
        txs = requests.get(f"{API}/transactions", params={
            "project_id": project["id"], "bank_account_id": nationwide["id"],
        }, timeout=15).json()
        assert txs and all(t.get("time") for t in txs), "all rows must have a time"
        # Group by date, ensure times are increasing (00:00:01, 00:00:02, ...).
        from collections import defaultdict
        by_date = defaultdict(list)
        for t in txs:
            by_date[t["date"]].append(t["time"])
        # Find a date with at least 2 tx to verify sequencing.
        multi = [(d, times) for d, times in by_date.items() if len(times) >= 2]
        assert multi, "expected at least one date with multiple transactions"
        for _d, times in multi:
            sorted_times = sorted(times)
            # All times unique and a contiguous run starting at 00:00:01.
            assert len(set(sorted_times)) == len(sorted_times), f"duplicate times: {sorted_times}"
            assert sorted_times[0] == "00:00:01", f"first time should be 00:00:01, got {sorted_times}"

    def test_bank_account_filter_on_listings(self, project):
        accts = requests.get(f"{API}/bank-accounts", params={"project_id": project["id"]}, timeout=15).json()
        nw = next(a for a in accts if a["name"] == "Nationwide")
        bos = next(a for a in accts if a["name"] == "Bank of Scotland")
        nw_tx = requests.get(f"{API}/transactions", params={
            "project_id": project["id"], "bank_account_id": nw["id"]}, timeout=15).json()
        bos_tx = requests.get(f"{API}/transactions", params={
            "project_id": project["id"], "bank_account_id": bos["id"]}, timeout=15).json()
        assert all(t["bank_account_id"] == nw["id"] for t in nw_tx)
        assert all(t["bank_account_id"] == bos["id"] for t in bos_tx)
        assert len(nw_tx) > 0 and len(bos_tx) > 0

        # Yearly analytics scoped to one account is a strict subset of overall.
        ya_all = requests.get(f"{API}/analytics/yearly", params={
            "project_id": project["id"], "year": 2026}, timeout=15).json()
        ya_nw = requests.get(f"{API}/analytics/yearly", params={
            "project_id": project["id"], "year": 2026, "bank_account_id": nw["id"]}, timeout=15).json()
        # Yearly response has monthly_income/monthly_expense arrays of length 12.
        assert "monthly_income" in ya_all and "monthly_expense" in ya_all
        assert "monthly_income" in ya_nw and "monthly_expense" in ya_nw
        # Account-scoped totals should be <= all-accounts totals month-by-month.
        for m in range(12):
            assert ya_nw["monthly_income"][m] <= ya_all["monthly_income"][m] + 0.001
            assert ya_nw["monthly_expense"][m] <= ya_all["monthly_expense"][m] + 0.001


# ─── (c) Sub-categories + one-level enforcement ─────────────────────────────


class TestSubCategories:
    @pytest.fixture(scope="class")
    def project(self):
        p = _make_project("Iter11_SubCat")
        yield p
        _delete_project(p["id"])

    def test_create_subcategory(self, project):
        parent = requests.post(f"{API}/categories", json={
            "project_id": project["id"], "name": "TEST_Transport", "type": "expense",
        }, timeout=15).json()
        child = requests.post(f"{API}/categories", json={
            "project_id": project["id"], "name": "TEST_Petrol", "type": "expense",
            "parent_id": parent["id"],
        }, timeout=15)
        assert child.status_code == 200, child.text
        assert child.json()["parent_id"] == parent["id"]

    def test_one_level_deep_enforced(self, project):
        cats = requests.get(f"{API}/categories", params={"project_id": project["id"]}, timeout=15).json()
        petrol = next(c for c in cats if c["name"] == "TEST_Petrol")
        r = requests.post(f"{API}/categories", json={
            "project_id": project["id"], "name": "TEST_Diesel", "type": "expense",
            "parent_id": petrol["id"],
        }, timeout=15)
        assert r.status_code == 400
        assert "one level deep" in r.json()["detail"].lower()

    def test_put_clears_parent_with_empty_string(self, project):
        cats = requests.get(f"{API}/categories", params={"project_id": project["id"]}, timeout=15).json()
        petrol = next(c for c in cats if c["name"] == "TEST_Petrol")
        r = requests.put(f"{API}/categories/{petrol['id']}", json={"parent_id": ""}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("parent_id") in (None, "")
        # And reattach for the next test.
        parent = next(c for c in cats if c["name"] == "TEST_Transport")
        requests.put(f"{API}/categories/{petrol['id']}", json={"parent_id": parent["id"]}, timeout=15)

    def test_delete_parent_detaches_children(self, project):
        cats = requests.get(f"{API}/categories", params={"project_id": project["id"]}, timeout=15).json()
        # Create an isolated parent+child to delete cleanly.
        p = requests.post(f"{API}/categories", json={
            "project_id": project["id"], "name": "TEST_ToDel", "type": "expense",
        }, timeout=15).json()
        c = requests.post(f"{API}/categories", json={
            "project_id": project["id"], "name": "TEST_ToDel_Child", "type": "expense",
            "parent_id": p["id"],
        }, timeout=15).json()
        r = requests.delete(f"{API}/categories/{p['id']}", timeout=15)
        assert r.status_code == 200
        cats_after = requests.get(f"{API}/categories", params={"project_id": project["id"]}, timeout=15).json()
        child_after = next((x for x in cats_after if x["id"] == c["id"]), None)
        assert child_after is not None, "child must NOT cascade-delete"
        assert child_after.get("parent_id") in (None, ""), "child parent_id must be NULL after parent delete"


# ─── (d) Budget roll-up: parent budget reflects child spend ─────────────────


class TestBudgetRollup:
    @pytest.fixture(scope="class")
    def setup(self):
        p = _make_project("Iter11_Rollup")
        pid = p["id"]
        # Parent + sub-category.
        parent = requests.post(f"{API}/categories", json={
            "project_id": pid, "name": "TEST_Transport_R", "type": "expense"}, timeout=15).json()
        child = requests.post(f"{API}/categories", json={
            "project_id": pid, "name": "TEST_Petrol_R", "type": "expense",
            "parent_id": parent["id"]}, timeout=15).json()
        # £200/month budget on the parent.
        b = requests.post(f"{API}/budgets", json={
            "project_id": pid, "category_id": parent["id"], "period": "monthly", "amount": 200.0
        }, timeout=15)
        assert b.status_code == 200, b.text
        yield {"project_id": pid, "parent": parent, "child": child}
        _delete_project(pid)

    def test_child_spend_rolls_into_parent_budget(self, setup):
        # Upload (any) PDF to make sure ingestion path is exercised, then insert
        # a synthetic £50 child-category transaction in the current month.
        now = datetime.utcnow()
        date_str = f"{now.year:04d}-{now.month:02d}-15"
        # Upload nationwide pdf so the project has an account, then create a CSV-ish tx via API:
        # No public POST endpoint for raw tx -- use the upload route with a minimal CSV.
        csv_bytes = (
            "Date,Description,Amount\n"
            f"{date_str},TEST_PETROL_PURCHASE,-50.00\n"
        ).encode()
        r = requests.post(
            f"{API}/transactions/upload",
            files={"file": ("petrol.csv", csv_bytes, "text/csv")},
            data={"project_id": setup["project_id"]},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        # Find the just-created tx and assign to the child sub-category.
        txs = requests.get(f"{API}/transactions", params={"project_id": setup["project_id"]}, timeout=15).json()
        target = next(t for t in txs if "TEST_PETROL_PURCHASE" in (t.get("description") or ""))
        u = requests.put(f"{API}/transactions/{target['id']}",
                         json={"category_id": setup["child"]["id"]}, timeout=15)
        assert u.status_code == 200, u.text

        # Now check progress for current month.
        prog = requests.get(f"{API}/budgets/progress", params={
            "project_id": setup["project_id"], "year": now.year, "month": now.month,
        }, timeout=15).json()
        assert "items" in prog
        parent_id = setup["parent"]["id"]
        child_id = setup["child"]["id"]
        # Parent budget must show spent=50 from the child transaction.
        parent_row = next((i for i in prog["items"] if i["category_id"] == parent_id), None)
        assert parent_row is not None, prog
        assert abs(parent_row["spent"] - 50.0) < 0.01, parent_row
        # The child has no budget, so it must not appear in the response.
        assert not any(i["category_id"] == child_id for i in prog["items"])


# ─── (e) Project cascade deletes bank_accounts ──────────────────────────────


def test_project_delete_cascades_bank_accounts():
    p = _make_project("Iter11_Cascade")
    pid = p["id"]
    a = requests.post(f"{API}/bank-accounts", json={
        "project_id": pid, "name": "Cascade", "sort_code": "10-20-30", "account_number": "99999999",
    }, timeout=15).json()
    assert a.get("id")
    requests.delete(f"{API}/projects/{pid}", timeout=15)
    # The account should now be gone.
    listing = requests.get(f"{API}/bank-accounts", params={"project_id": pid}, timeout=15).json()
    assert listing == []
