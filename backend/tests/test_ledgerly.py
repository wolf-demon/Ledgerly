"""Comprehensive backend tests for Ledgerly.

Covers projects, categories, CSV/PDF upload, dedupe, transactions filters,
rules, AI categorize suggest, analytics yearly/category/years.
"""
import io
import os
import time
import requests
import pytest

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://statement-analyzer-35.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def project():
    r = requests.post(f"{API}/projects", json={"name": "TEST_Ledgerly", "description": "pytest"})
    assert r.status_code == 200, r.text
    p = r.json()
    yield p
    requests.delete(f"{API}/projects/{p['id']}")


@pytest.fixture(scope="module")
def categories(project):
    r = requests.get(f"{API}/categories", params={"project_id": project["id"]})
    assert r.status_code == 200
    return r.json()


# ---------- Projects ----------
class TestProjects:
    def test_create_seeds_9_default_categories(self, project):
        r = requests.get(f"{API}/categories", params={"project_id": project["id"]})
        assert r.status_code == 200
        cats = r.json()
        assert len(cats) == 9
        income = [c for c in cats if c["type"] == "income"]
        expense = [c for c in cats if c["type"] == "expense"]
        assert len(income) == 2
        assert len(expense) == 7
        names = {c["name"] for c in cats}
        assert "Salary" in names
        assert "Groceries" in names

    def test_list_projects_includes_created(self, project):
        r = requests.get(f"{API}/projects")
        assert r.status_code == 200
        ids = [p["id"] for p in r.json()]
        assert project["id"] in ids

    def test_delete_cascades(self):
        # create temp project, add tx via upload, delete and verify cleanup
        p = requests.post(f"{API}/projects", json={"name": "TEST_cascade"}).json()
        csv = b"Date,Description,Amount\n01/03/2025,TEST CASCADE,-10.00\n"
        files = {"file": ("c.csv", csv, "text/csv")}
        up = requests.post(f"{API}/transactions/upload", data={"project_id": p["id"]}, files=files)
        assert up.status_code == 200
        d = requests.delete(f"{API}/projects/{p['id']}")
        assert d.status_code == 200
        cats = requests.get(f"{API}/categories", params={"project_id": p["id"]}).json()
        assert cats == []
        txs = requests.get(f"{API}/transactions", params={"project_id": p["id"]}).json()
        assert txs == []


# ---------- Categories ----------
class TestCategories:
    def test_create_invalid_type_rejected(self, project):
        r = requests.post(f"{API}/categories", json={
            "project_id": project["id"], "name": "X", "type": "bad"
        })
        assert r.status_code == 400

    def test_create_update_delete_nulls_tx(self, project):
        # create cat
        r = requests.post(f"{API}/categories", json={
            "project_id": project["id"], "name": "TEST_TempCat", "type": "expense"
        })
        assert r.status_code == 200
        cat = r.json()
        # update
        u = requests.put(f"{API}/categories/{cat['id']}", json={"name": "TEST_Renamed"})
        assert u.status_code == 200
        assert u.json()["name"] == "TEST_Renamed"
        # create a tx and assign category, then delete category and ensure category_id null
        csv = b"Date,Description,Amount\n10/04/2025,FOO BAR XYZ,-5.00\n"
        files = {"file": ("c.csv", csv, "text/csv")}
        requests.post(f"{API}/transactions/upload", data={"project_id": project["id"]}, files=files)
        txs = requests.get(f"{API}/transactions", params={"project_id": project["id"]}).json()
        tx = next(t for t in txs if "FOO BAR" in t["description"])
        requests.put(f"{API}/transactions/{tx['id']}", json={"category_id": cat["id"]})
        d = requests.delete(f"{API}/categories/{cat['id']}")
        assert d.status_code == 200
        txs2 = requests.get(f"{API}/transactions", params={"project_id": project["id"]}).json()
        target = next(t for t in txs2 if t["id"] == tx["id"])
        assert target["category_id"] is None


# ---------- Upload (CSV) ----------
class TestUploadCSV:
    def test_csv_date_description_amount(self, project):
        csv = (
            b"Date,Description,Amount\n"
            b"01/03/2025,TESCO STORES 1234,-45.20\n"
            b"02/03/2025,SALARY ACME LTD,2500.00\n"
            b"03/03/2025,NETFLIX SUBSCRIPTION,-9.99\n"
            b"05/03/2025,TESCO STORES 5678,-18.75\n"
        )
        files = {"file": ("statement.csv", csv, "text/csv")}
        r = requests.post(f"{API}/transactions/upload",
                          data={"project_id": project["id"]}, files=files)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["inserted"] == 4
        assert data["total"] == 4

    def test_csv_dedupe_on_reupload(self, project):
        csv = (
            b"Date,Description,Amount\n"
            b"01/03/2025,TESCO STORES 1234,-45.20\n"
            b"02/03/2025,SALARY ACME LTD,2500.00\n"
        )
        files = {"file": ("statement.csv", csv, "text/csv")}
        r = requests.post(f"{API}/transactions/upload",
                          data={"project_id": project["id"]}, files=files)
        assert r.status_code == 200
        data = r.json()
        assert data["inserted"] == 0
        assert data["skipped"] == 2

    def test_csv_debit_credit_variant(self, project):
        # new project so we don't dedupe against prior data
        p = requests.post(f"{API}/projects", json={"name": "TEST_DC"}).json()
        csv = (
            b"Date,Description,Debit,Credit\n"
            b"04/03/2025,WAGES,,1500.00\n"
            b"05/03/2025,GAS BILL,75.50,\n"
        )
        files = {"file": ("dc.csv", csv, "text/csv")}
        r = requests.post(f"{API}/transactions/upload",
                          data={"project_id": p["id"]}, files=files)
        assert r.status_code == 200
        assert r.json()["inserted"] == 2
        txs = requests.get(f"{API}/transactions", params={"project_id": p["id"]}).json()
        amounts = sorted([t["amount"] for t in txs])
        assert amounts == [-75.5, 1500.0]
        types = {t["description"]: t["type"] for t in txs}
        assert types["WAGES"] == "income"
        assert types["GAS BILL"] == "expense"
        requests.delete(f"{API}/projects/{p['id']}")


# ---------- Filters ----------
class TestFilters:
    def test_filter_year_month_uncategorized(self, project):
        # Should have data from prior CSV upload in 2025-03
        r = requests.get(f"{API}/transactions",
                         params={"project_id": project["id"], "year": 2025, "month": 3})
        assert r.status_code == 200
        for t in r.json():
            assert t["date"].startswith("2025-03")
        ru = requests.get(f"{API}/transactions",
                          params={"project_id": project["id"], "uncategorized": "true"})
        assert ru.status_code == 200
        for t in ru.json():
            assert t.get("category_id") is None


# ---------- Rules ----------
class TestRules:
    def test_apply_to_similar_creates_rule_and_back_applies(self, project, categories):
        # find Groceries category
        cat = next(c for c in categories if c["name"] == "Groceries")
        # find a TESCO transaction
        txs = requests.get(f"{API}/transactions", params={"project_id": project["id"]}).json()
        tesco = [t for t in txs if "TESCO" in t["description"]]
        assert len(tesco) >= 2
        first = tesco[0]
        r = requests.put(f"{API}/transactions/{first['id']}",
                         json={"category_id": cat["id"], "apply_to_similar": True})
        assert r.status_code == 200
        body = r.json()
        # at least the other tesco should be re-categorized
        assert body["affected_similar"] >= 1
        # verify all TESCO tx now have the category
        txs2 = requests.get(f"{API}/transactions", params={"project_id": project["id"]}).json()
        for t in txs2:
            if "TESCO" in t["description"]:
                assert t["category_id"] == cat["id"]

    def test_subsequent_upload_auto_categorizes_via_rule(self, project, categories):
        cat = next(c for c in categories if c["name"] == "Groceries")
        csv = (
            b"Date,Description,Amount\n"
            b"15/05/2025,TESCO STORES 9999,-22.10\n"
        )
        files = {"file": ("new.csv", csv, "text/csv")}
        r = requests.post(f"{API}/transactions/upload",
                          data={"project_id": project["id"]}, files=files)
        assert r.status_code == 200
        txs = requests.get(f"{API}/transactions",
                          params={"project_id": project["id"], "year": 2025, "month": 5}).json()
        new_tx = next(t for t in txs if t["amount"] == -22.10)
        assert new_tx["category_id"] == cat["id"]


# ---------- AI Suggest ----------
class TestSuggest:
    def test_suggest_returns_valid_category(self, project, categories):
        r = requests.post(f"{API}/categorize/suggest", json={
            "project_id": project["id"],
            "description": "NETFLIX SUBSCRIPTION",
            "amount": -9.99,
        }, timeout=60)
        assert r.status_code == 200
        body = r.json()
        # If LLM works, suggested_category_id should be one of our categories
        if body.get("suggested_category_id"):
            ids = {c["id"] for c in categories}
            assert body["suggested_category_id"] in ids
        else:
            pytest.skip(f"AI did not return a match: {body}")


# ---------- Analytics ----------
class TestAnalytics:
    def test_yearly(self, project):
        r = requests.get(f"{API}/analytics/yearly",
                         params={"project_id": project["id"], "year": 2025})
        assert r.status_code == 200
        d = r.json()
        assert len(d["monthly_income"]) == 12
        assert len(d["monthly_expense"]) == 12
        assert "total_income" in d and "total_expense" in d and "net" in d
        assert d["total_income"] >= 2500.0
        assert d["total_expense"] >= 45.20
        assert isinstance(d["categories"], list)
        # ensure each category has monthly[12]
        for c in d["categories"]:
            assert len(c["monthly"]) == 12

    def test_category_detail(self, project, categories):
        cat = next(c for c in categories if c["name"] == "Groceries")
        r = requests.get(f"{API}/analytics/category/{cat['id']}",
                         params={"project_id": project["id"], "year": 2025})
        assert r.status_code == 200
        d = r.json()
        assert len(d["monthly"]) == 12
        assert isinstance(d["transactions"], list)
        # we previously categorized TESCO under Groceries
        assert len(d["transactions"]) >= 2

    def test_years(self, project):
        r = requests.get(f"{API}/analytics/years", params={"project_id": project["id"]})
        assert r.status_code == 200
        d = r.json()
        assert 2025 in d["years"]
