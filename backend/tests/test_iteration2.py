"""Iteration 2 backend tests: bulk-categorize, CSV export, recurring analytics, yearly uncategorized split."""
import io
import os
import requests
import pytest

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"

SAMPLE_CSV = (
    b"Date,Description,Amount\n"
    b"05/01/2025,NETFLIX SUBSCRIPTION,-9.99\n"
    b"05/02/2025,NETFLIX SUBSCRIPTION,-9.99\n"
    b"05/03/2025,NETFLIX SUBSCRIPTION,-9.99\n"
    b"01/01/2025,SALARY ACME LTD,2500.00\n"
    b"01/02/2025,SALARY ACME LTD,2500.00\n"
    b"01/03/2025,SALARY ACME LTD,2500.00\n"
    b"10/01/2025,TESCO STORES 1,-45.20\n"
    b"12/02/2025,TESCO STORES 2,-52.00\n"
)


@pytest.fixture(scope="module")
def project():
    r = requests.post(f"{API}/projects", json={"name": "TEST_Iter2", "description": "iter2"})
    assert r.status_code == 200
    p = r.json()
    files = {"file": ("seed.csv", SAMPLE_CSV, "text/csv")}
    up = requests.post(f"{API}/transactions/upload", data={"project_id": p["id"]}, files=files)
    assert up.status_code == 200
    yield p
    requests.delete(f"{API}/projects/{p['id']}")


@pytest.fixture(scope="module")
def categories(project):
    r = requests.get(f"{API}/categories", params={"project_id": project["id"]})
    return r.json()


# ---------- Bulk categorize ----------
class TestBulkCategorize:
    def test_bulk_no_ids_400(self, project, categories):
        cat = next(c for c in categories if c["name"] == "Groceries")
        r = requests.post(f"{API}/transactions/bulk-categorize", json={
            "transaction_ids": [], "category_id": cat["id"]
        })
        assert r.status_code == 400

    def test_bulk_invalid_category_404(self, project):
        r = requests.post(f"{API}/transactions/bulk-categorize", json={
            "transaction_ids": ["x"], "category_id": "not-a-real-id"
        })
        assert r.status_code == 404

    def test_bulk_categorize_with_apply_to_similar(self, project, categories):
        cat = next(c for c in categories if c["name"] == "Entertainment")
        txs = requests.get(f"{API}/transactions", params={"project_id": project["id"]}).json()
        netflix = [t for t in txs if "NETFLIX" in t["description"]]
        assert len(netflix) >= 3
        # pick one netflix tx; with apply_to_similar should backfill others
        target_id = netflix[0]["id"]
        r = requests.post(f"{API}/transactions/bulk-categorize", json={
            "transaction_ids": [target_id],
            "category_id": cat["id"],
            "apply_to_similar": True,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["updated"] == 1
        # others should be back-applied
        assert body["similar_applied"] >= 2
        assert body["rules_added"] >= 1
        # verify all NETFLIX are now Entertainment
        txs2 = requests.get(f"{API}/transactions", params={"project_id": project["id"]}).json()
        for t in txs2:
            if "NETFLIX" in t["description"]:
                assert t["category_id"] == cat["id"]

    def test_bulk_categorize_multiple_ids_no_rule(self, project, categories):
        cat = next(c for c in categories if c["name"] == "Salary")
        txs = requests.get(f"{API}/transactions", params={"project_id": project["id"]}).json()
        salary = [t for t in txs if "SALARY" in t["description"]]
        assert len(salary) == 3
        ids = [t["id"] for t in salary]
        r = requests.post(f"{API}/transactions/bulk-categorize", json={
            "transaction_ids": ids,
            "category_id": cat["id"],
            "apply_to_similar": False,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["updated"] == 3
        assert body["rules_added"] == 0
        # verify
        txs2 = requests.get(f"{API}/transactions", params={"project_id": project["id"]}).json()
        for t in txs2:
            if "SALARY" in t["description"]:
                assert t["category_id"] == cat["id"]


# ---------- CSV Export ----------
class TestExport:
    def test_export_basic_headers(self, project):
        r = requests.get(f"{API}/transactions/export", params={"project_id": project["id"]})
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert "filename=" in cd
        text = r.text.splitlines()
        # header row
        header = text[0]
        assert "Date" in header and "Description" in header and "Category" in header and "Type" in header and "Amount" in header
        # at least one row
        assert len(text) > 1

    def test_export_year_filter(self, project):
        r = requests.get(f"{API}/transactions/export", params={"project_id": project["id"], "year": 2025})
        assert r.status_code == 200
        rows = r.text.splitlines()[1:]
        for row in rows:
            assert row.startswith("2025-")
        # year that has no data should produce only header
        r2 = requests.get(f"{API}/transactions/export", params={"project_id": project["id"], "year": 1999})
        assert r2.status_code == 200
        assert len(r2.text.strip().splitlines()) == 1

    def test_export_uncategorized_label(self):
        # fresh project to ensure all uncategorized
        p = requests.post(f"{API}/projects", json={"name": "TEST_ExportUncat"}).json()
        files = {"file": ("e.csv", b"Date,Description,Amount\n01/04/2025,FOO BAR Q,-12.34\n", "text/csv")}
        requests.post(f"{API}/transactions/upload", data={"project_id": p["id"]}, files=files)
        r = requests.get(f"{API}/transactions/export", params={"project_id": p["id"]})
        assert r.status_code == 200
        assert "Uncategorized" in r.text
        requests.delete(f"{API}/projects/{p['id']}")


# ---------- Recurring analytics ----------
class TestRecurring:
    def test_recurring_detects_monthly(self, project):
        r = requests.get(f"{API}/analytics/recurring", params={"project_id": project["id"], "lookback_months": 12})
        assert r.status_code == 200
        data = r.json()
        assert "recurring" in data and "forecast" in data
        keys = {item["merchant_key"] for item in data["recurring"]}
        # Expect NETFLIX and SALARY at least (>=2 distinct months)
        assert any("NETFLIX" in k for k in keys), keys
        assert any("SALARY" in k for k in keys), keys
        for item in data["recurring"]:
            assert item["cadence"] in ("weekly", "fortnightly", "monthly", "quarterly", "irregular")
            assert "avg_gap_days" in item
            assert "monthly_estimate" in item
            assert "next_expected" in item
            assert "last_seen" in item
            assert "category_name" in item
            assert item["type"] in ("income", "expense")
        # forecast totals
        fc = data["forecast"]
        assert fc["monthly_total_expense"] >= 9.99
        assert fc["monthly_total_income"] >= 2500.0
        assert "monthly_net" in fc

    def test_recurring_lookback_filter(self, project):
        # short lookback should reduce results (only most recent months)
        r = requests.get(f"{API}/analytics/recurring", params={"project_id": project["id"], "lookback_months": 1})
        assert r.status_code == 200
        # with only 1 month lookback, should be 0 recurring (need 2+ distinct months)
        assert r.json()["recurring"] == []

    def test_recurring_empty_project(self):
        p = requests.post(f"{API}/projects", json={"name": "TEST_EmptyRec"}).json()
        r = requests.get(f"{API}/analytics/recurring", params={"project_id": p["id"]})
        assert r.status_code == 200
        d = r.json()
        assert d["recurring"] == []
        assert d["forecast"]["monthly_total_expense"] == 0.0
        requests.delete(f"{API}/projects/{p['id']}")


# ---------- Yearly uncategorized split ----------
class TestYearlyUncatSplit:
    def test_uncategorized_split_into_income_and_expense(self):
        p = requests.post(f"{API}/projects", json={"name": "TEST_YearlySplit"}).json()
        csv = (
            b"Date,Description,Amount\n"
            b"01/01/2025,RANDOM INCOME,500.00\n"
            b"02/01/2025,RANDOM EXPENSE,-75.00\n"
        )
        files = {"file": ("y.csv", csv, "text/csv")}
        up = requests.post(f"{API}/transactions/upload", data={"project_id": p["id"]}, files=files)
        assert up.status_code == 200
        r = requests.get(f"{API}/analytics/yearly", params={"project_id": p["id"], "year": 2025})
        assert r.status_code == 200
        cats = r.json()["categories"]
        uncat = [c for c in cats if c["name"] == "Uncategorized"]
        types = {c["type"] for c in uncat}
        assert "income" in types, uncat
        assert "expense" in types, uncat
        for c in uncat:
            assert c["category_id"] is None
            assert c["color"] == "#999999"
            assert len(c["monthly"]) == 12
            if c["type"] == "income":
                assert c["total"] == 500.0
            else:
                assert c["total"] == -75.0
        requests.delete(f"{API}/projects/{p['id']}")
