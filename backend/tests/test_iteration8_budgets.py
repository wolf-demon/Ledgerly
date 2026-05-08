"""Iteration 8 backend tests: Budget tracker feature.

Covers:
  - GET /budgets list (empty + populated)
  - POST /budgets upsert (insert, update, period uniqueness, amount=0 deletion)
  - POST /budgets validation (period, amount, category ownership)
  - DELETE /budgets/{id}
  - GET /budgets/progress (no tx, exact, warn, over thresholds)
  - Rollover monthly math (with prior tx + with no prior tx)
  - Cascade delete via project + category
  - Income category target progress
"""
import os
import sys
import requests
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"


# ---------- Fixtures ----------
@pytest.fixture
def project():
    r = requests.post(f"{API}/projects", json={"name": "TEST_Iter8_Budgets", "description": "iter8"})
    assert r.status_code == 200
    p = r.json()
    yield p
    requests.delete(f"{API}/projects/{p['id']}")


def _make_cat(project_id, name, ctype):
    r = requests.post(f"{API}/categories", json={
        "project_id": project_id, "name": name, "type": ctype, "color": "#364C2E"
    })
    assert r.status_code == 200, r.text
    return r.json()


def _upload(project_id, csv_bytes):
    r = requests.post(
        f"{API}/transactions/upload",
        data={"project_id": project_id},
        files={"file": ("a.csv", csv_bytes, "text/csv")},
    )
    assert r.status_code == 200, r.text


def _categorize_all(project_id, category_id):
    """Assign every transaction in project to a category (force flip)."""
    txs = requests.get(f"{API}/transactions", params={"project_id": project_id}).json()
    for t in txs:
        requests.put(f"{API}/transactions/{t['id']}",
                     json={"category_id": category_id})


# ---------- list_budgets / upsert / delete ----------
class TestBudgetsCRUD:
    def test_empty_list_on_fresh_project(self, project):
        r = requests.get(f"{API}/budgets", params={"project_id": project["id"]})
        assert r.status_code == 200
        assert r.json() == []

    def test_upsert_insert_then_update_no_duplicate(self, project):
        cat = _make_cat(project["id"], "TEST_Groc", "expense")
        # Insert
        r = requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 500, "rollover": False,
        })
        assert r.status_code == 200
        b1 = r.json()
        assert b1["amount"] == 500
        assert b1["period"] == "monthly"
        assert b1["rollover"] is False

        # Update same (project, cat, period) -- should NOT duplicate, same id
        r = requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 600, "rollover": True,
        })
        assert r.status_code == 200
        b2 = r.json()
        assert b2["id"] == b1["id"]
        assert b2["amount"] == 600
        assert b2["rollover"] is True

        # Verify only one row
        listing = requests.get(f"{API}/budgets", params={"project_id": project["id"]}).json()
        assert len(listing) == 1
        assert listing[0]["amount"] == 600

    def test_different_period_creates_separate_row(self, project):
        cat = _make_cat(project["id"], "TEST_Rent", "expense")
        requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 100,
        })
        requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "yearly", "amount": 1200,
        })
        listing = requests.get(f"{API}/budgets", params={"project_id": project["id"]}).json()
        periods = sorted(b["period"] for b in listing)
        assert periods == ["monthly", "yearly"]

    def test_amount_zero_deletes(self, project):
        cat = _make_cat(project["id"], "TEST_Zero", "expense")
        requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 200,
        })
        # Confirm exists
        listing = requests.get(f"{API}/budgets", params={"project_id": project["id"]}).json()
        assert len(listing) == 1

        r = requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 0,
        })
        assert r.status_code == 200

        listing2 = requests.get(f"{API}/budgets", params={"project_id": project["id"]}).json()
        assert listing2 == []

    def test_validations(self, project):
        cat = _make_cat(project["id"], "TEST_Val", "expense")
        # Bad period
        r = requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "weekly", "amount": 10,
        })
        assert r.status_code == 400

        # Negative amount
        r = requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": -5,
        })
        assert r.status_code == 400

        # Category not in project
        r = requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": "nonexistent-cat-id",
            "period": "monthly", "amount": 50,
        })
        assert r.status_code == 404

    def test_delete_endpoint(self, project):
        cat = _make_cat(project["id"], "TEST_Del", "expense")
        r = requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 100,
        })
        bid = r.json()["id"]
        r = requests.delete(f"{API}/budgets/{bid}")
        assert r.status_code == 200
        listing = requests.get(f"{API}/budgets", params={"project_id": project["id"]}).json()
        assert listing == []


# ---------- progress ----------
class TestBudgetsProgress:
    def test_progress_no_tx_ok(self, project):
        cat = _make_cat(project["id"], "TEST_NoTx", "expense")
        requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 500,
        })
        r = requests.get(f"{API}/budgets/progress",
                        params={"project_id": project["id"], "year": 2025, "month": 3})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        it = items[0]
        assert it["spent"] == 0
        assert it["percent"] == 0
        assert it["status"] == "ok"
        assert it["effective_amount"] == 500

    def test_progress_over_status(self, project):
        cat = _make_cat(project["id"], "TEST_Over", "expense")
        # Tiny budget vs significant spend
        _upload(project["id"], b"Date,Description,Amount\n15/03/2025,TEST_OVERSPEND,-200.00\n")
        _categorize_all(project["id"], cat["id"])
        requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 1,
        })
        r = requests.get(f"{API}/budgets/progress",
                        params={"project_id": project["id"], "year": 2025, "month": 3})
        items = r.json()["items"]
        it = next(i for i in items if i["category_id"] == cat["id"])
        assert it["status"] == "over"
        assert it["percent"] >= 100

    def test_progress_warn_status(self, project):
        cat = _make_cat(project["id"], "TEST_Warn", "expense")
        # spend 85 of 100 -> 85% -> warn
        _upload(project["id"], b"Date,Description,Amount\n10/03/2025,TEST_WARN,-85.00\n")
        _categorize_all(project["id"], cat["id"])
        requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 100,
        })
        r = requests.get(f"{API}/budgets/progress",
                        params={"project_id": project["id"], "year": 2025, "month": 3})
        items = r.json()["items"]
        it = next(i for i in items if i["category_id"] == cat["id"])
        assert it["status"] == "warn"
        assert 80 <= it["percent"] < 100


# ---------- rollover math ----------
class TestRollover:
    def test_rollover_with_prior_tx(self, project):
        cat = _make_cat(project["id"], "TEST_RollGroc", "expense")
        # Jan: -50 (leftover 450), Feb: 0 (leftover 500)
        _upload(project["id"],
                b"Date,Description,Amount\n15/01/2025,TEST_ROLL_JAN,-50.00\n")
        _categorize_all(project["id"], cat["id"])
        requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 500, "rollover": True,
        })
        r = requests.get(f"{API}/budgets/progress",
                        params={"project_id": project["id"], "year": 2025, "month": 3})
        items = r.json()["items"]
        it = next(i for i in items if i["category_id"] == cat["id"])
        # Should be > base amount (rolled over leftover from Jan + Feb at minimum)
        assert it["effective_amount"] > 500
        # Sensible upper bound: cap is 11 months back, all months 0->500 each ⇒ 500 + 11*500 = 6000
        # Real: 500 (base) + 450 (Jan) + 500 (Feb) + earlier zero-tx months back to prev year (each 500) = should be sensible
        assert it["effective_amount"] <= 500 * 12

    def test_rollover_no_prior_tx_caps_at_12x(self, project):
        cat = _make_cat(project["id"], "TEST_RollClean", "expense")
        # No prior transactions for this category whatsoever
        requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 100, "rollover": True,
        })
        r = requests.get(f"{API}/budgets/progress",
                        params={"project_id": project["id"], "year": 2025, "month": 3})
        items = r.json()["items"]
        it = next(i for i in items if i["category_id"] == cat["id"])
        # base 100 + 11 carried (each full 100) = 1200
        assert it["effective_amount"] == pytest.approx(1200, abs=0.01)


# ---------- cascade delete ----------
class TestCascadeDelete:
    def test_delete_category_removes_budget(self, project):
        cat = _make_cat(project["id"], "TEST_CascCat", "expense")
        requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 100,
        })
        listing = requests.get(f"{API}/budgets", params={"project_id": project["id"]}).json()
        assert any(b["category_id"] == cat["id"] for b in listing)

        r = requests.delete(f"{API}/categories/{cat['id']}")
        assert r.status_code == 200

        listing2 = requests.get(f"{API}/budgets", params={"project_id": project["id"]}).json()
        assert not any(b["category_id"] == cat["id"] for b in listing2)

    def test_delete_project_removes_all_budgets(self):
        r = requests.post(f"{API}/projects", json={"name": "TEST_CascProj", "description": "x"})
        proj = r.json()
        cat = _make_cat(proj["id"], "TEST_PCC", "expense")
        requests.post(f"{API}/budgets", json={
            "project_id": proj["id"], "category_id": cat["id"],
            "period": "monthly", "amount": 50,
        })
        # Delete project
        r = requests.delete(f"{API}/projects/{proj['id']}")
        assert r.status_code == 200
        # GET budgets for that project_id should be empty
        listing = requests.get(f"{API}/budgets", params={"project_id": proj["id"]}).json()
        assert listing == []


# ---------- income category as target ----------
class TestIncomeTarget:
    def test_income_progress_uses_received_as_spent(self, project):
        inc = _make_cat(project["id"], "TEST_Salary", "income")
        # +800 in March
        _upload(project["id"], b"Date,Description,Amount\n05/03/2025,TEST_SAL,800.00\n")
        _categorize_all(project["id"], inc["id"])
        requests.post(f"{API}/budgets", json={
            "project_id": project["id"], "category_id": inc["id"],
            "period": "monthly", "amount": 1000,
        })
        r = requests.get(f"{API}/budgets/progress",
                        params={"project_id": project["id"], "year": 2025, "month": 3})
        items = r.json()["items"]
        it = next(i for i in items if i["category_id"] == inc["id"])
        assert it["spent"] == pytest.approx(800, abs=0.01)
        assert it["percent"] == pytest.approx(80.0, abs=0.5)
        assert it["status"] == "warn"
        assert it["remaining"] == pytest.approx(200, abs=0.01)
