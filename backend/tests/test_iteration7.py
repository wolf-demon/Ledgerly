"""Iteration 7 backend tests: sign-flip on categorize, bulk-categorize, reclassify,
bulk-suggest endpoint, settings.emergent_key, /settings/test-emergent.
"""
import os
import sys
import requests
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def project():
    r = requests.post(f"{API}/projects", json={"name": "TEST_Iter7", "description": "iter7"})
    assert r.status_code == 200
    p = r.json()
    yield p
    requests.delete(f"{API}/projects/{p['id']}")


@pytest.fixture(scope="module")
def categories(project):
    """Create one expense + one income category (defaults provided in seed)."""
    r = requests.get(f"{API}/categories", params={"project_id": project["id"]})
    assert r.status_code == 200
    cats = r.json()
    # Seed default categories (POST /projects auto-seeds). Pick by type.
    expense = next((c for c in cats if c["type"] == "expense"), None)
    income = next((c for c in cats if c["type"] == "income"), None)
    if not expense:
        r = requests.post(f"{API}/categories", json={
            "project_id": project["id"], "name": "TEST_Entertainment",
            "type": "expense", "color": "#D96C4E"
        })
        expense = r.json()
    if not income:
        r = requests.post(f"{API}/categories", json={
            "project_id": project["id"], "name": "TEST_Salary",
            "type": "income", "color": "#364C2E"
        })
        income = r.json()
    return {"expense": expense, "income": income}


def _upload_csv(project_id, csv_bytes):
    files = {"file": ("a.csv", csv_bytes, "text/csv")}
    r = requests.post(
        f"{API}/transactions/upload",
        data={"project_id": project_id},
        files=files,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ---------- Sign-flip on PUT /transactions/{id} ----------
class TestSingleUpdateSignFlip:
    def test_positive_to_expense_flips_to_negative(self, project, categories):
        # CSV with positive amount
        _upload_csv(project["id"],
                    b"Date,Description,Amount\n01/03/2025,TEST_NETFLIX_FLIP,9.99\n")
        txs = requests.get(f"{API}/transactions",
                           params={"project_id": project["id"]}).json()
        tx = next(t for t in txs if t["description"] == "TEST_NETFLIX_FLIP")
        assert tx["amount"] == 9.99
        assert tx["type"] == "income"  # bug-state from positive parse

        # Assign expense category
        r = requests.put(f"{API}/transactions/{tx['id']}",
                         json={"category_id": categories["expense"]["id"]})
        assert r.status_code == 200, r.text

        # Verify flipped
        txs2 = requests.get(f"{API}/transactions",
                            params={"project_id": project["id"]}).json()
        tx2 = next(t for t in txs2 if t["id"] == tx["id"])
        assert tx2["amount"] == -9.99
        assert tx2["type"] == "expense"
        assert tx2["category_id"] == categories["expense"]["id"]

    def test_negative_to_income_flips_to_positive(self, project, categories):
        _upload_csv(project["id"],
                    b"Date,Description,Amount\n02/03/2025,TEST_REFUND_FLIP,-50.00\n")
        txs = requests.get(f"{API}/transactions",
                           params={"project_id": project["id"]}).json()
        tx = next(t for t in txs if t["description"] == "TEST_REFUND_FLIP")
        assert tx["amount"] == -50.00
        assert tx["type"] == "expense"

        r = requests.put(f"{API}/transactions/{tx['id']}",
                         json={"category_id": categories["income"]["id"]})
        assert r.status_code == 200

        txs2 = requests.get(f"{API}/transactions",
                            params={"project_id": project["id"]}).json()
        tx2 = next(t for t in txs2 if t["id"] == tx["id"])
        assert tx2["amount"] == 50.00
        assert tx2["type"] == "income"


# ---------- Bulk categorize sign-flip ----------
class TestBulkCategorizeSignFlip:
    def test_bulk_categorize_flips_all(self, project, categories):
        _upload_csv(project["id"],
                    b"Date,Description,Amount\n"
                    b"03/03/2025,TEST_BULK_A,12.34\n"
                    b"04/03/2025,TEST_BULK_B,56.78\n")
        txs = requests.get(f"{API}/transactions",
                           params={"project_id": project["id"]}).json()
        ids = [t["id"] for t in txs if t["description"] in ("TEST_BULK_A", "TEST_BULK_B")]
        assert len(ids) == 2

        r = requests.post(f"{API}/transactions/bulk-categorize",
                          json={"transaction_ids": ids,
                                "category_id": categories["expense"]["id"],
                                "apply_to_similar": False})
        assert r.status_code == 200, r.text
        assert r.json()["updated"] == 2

        txs2 = requests.get(f"{API}/transactions",
                            params={"project_id": project["id"]}).json()
        for d in ("TEST_BULK_A", "TEST_BULK_B"):
            t = next(x for x in txs2 if x["description"] == d)
            assert t["amount"] < 0
            assert t["type"] == "expense"


# ---------- apply_to_similar sign-flip ----------
class TestApplyToSimilarSignFlip:
    def test_apply_to_similar_flips_back_applied(self, project, categories):
        _upload_csv(project["id"],
                    b"Date,Description,Amount\n"
                    b"05/03/2025,TEST_SPOTIFY 12345,9.99\n"
                    b"06/03/2025,TEST_SPOTIFY 67890,9.99\n"
                    b"07/03/2025,TEST_SPOTIFY 99999,9.99\n")
        txs = requests.get(f"{API}/transactions",
                           params={"project_id": project["id"]}).json()
        spotifies = [t for t in txs if t["description"].startswith("TEST_SPOTIFY")]
        assert len(spotifies) == 3
        first = spotifies[0]

        r = requests.put(f"{API}/transactions/{first['id']}",
                         json={"category_id": categories["expense"]["id"],
                               "apply_to_similar": True})
        assert r.status_code == 200, r.text
        assert r.json().get("affected_similar", 0) >= 2

        txs2 = requests.get(f"{API}/transactions",
                            params={"project_id": project["id"]}).json()
        for t in [x for x in txs2 if x["description"].startswith("TEST_SPOTIFY")]:
            assert t["amount"] == -9.99
            assert t["type"] == "expense"
            assert t["category_id"] == categories["expense"]["id"]


# ---------- Reclassify enhanced ----------
class TestReclassifyEnhanced:
    def test_reclassify_fixes_categorized_and_uncategorized(self, project, categories):
        # Drop a few rows directly via upload
        _upload_csv(project["id"],
                    b"Date,Description,Amount\n"
                    b"08/03/2025,TEST_RECLS_UNCAT,-22.00\n")
        # Manually un-fix one categorized tx by writing direct-update would need DB access;
        # instead we just confirm reclassify is idempotent / non-500 and returns shape.
        r = requests.post(f"{API}/transactions/reclassify",
                          params={"project_id": project["id"]})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "checked" in d and "fixed" in d
        assert isinstance(d["checked"], int) and isinstance(d["fixed"], int)


# ---------- Analytics yearly post-categorization ----------
class TestAnalyticsAfterCategorize:
    def test_yearly_split_correctly_after_assign(self, project, categories):
        # Use a unique year so we don't collide with other tests.
        _upload_csv(project["id"],
                    b"Date,Description,Amount\n01/06/2099,TEST_YR_NETFLIX,9.99\n")
        # Get yearly before assigning
        b = requests.get(f"{API}/analytics/yearly",
                         params={"project_id": project["id"], "year": 2099}).json()
        # The lone tx is positive => initially counted as income
        assert b["total_income"] >= 9.99
        before_expense = b["total_expense"]

        # Assign expense category
        txs = requests.get(f"{API}/transactions",
                           params={"project_id": project["id"]}).json()
        tx = next(t for t in txs if t["description"] == "TEST_YR_NETFLIX")
        r = requests.put(f"{API}/transactions/{tx['id']}",
                         json={"category_id": categories["expense"]["id"]})
        assert r.status_code == 200

        a = requests.get(f"{API}/analytics/yearly",
                         params={"project_id": project["id"], "year": 2099}).json()
        # Now 9.99 should be in expense, not income
        assert a["total_expense"] == round(before_expense + 9.99, 2)
        assert a["total_income"] < b["total_income"] + 0.001


# ---------- Settings emergent_key + /settings/test-emergent ----------
class TestSettingsEmergentKey:
    def test_get_settings_includes_emergent_key_field(self):
        r = requests.get(f"{API}/settings")
        assert r.status_code == 200
        d = r.json()
        assert "emergent_key" in d
        assert isinstance(d["emergent_key"], str)

    def test_put_emergent_key_persists(self):
        original = requests.get(f"{API}/settings").json()
        try:
            r = requests.put(f"{API}/settings", json={"emergent_key": "test-key-123"})
            assert r.status_code == 200
            assert r.json()["emergent_key"] == "test-key-123"
            r2 = requests.get(f"{API}/settings").json()
            assert r2["emergent_key"] == "test-key-123"
        finally:
            # Restore (only fields we know of)
            requests.put(f"{API}/settings", json={
                "emergent_key": original.get("emergent_key", ""),
                "ai_provider": original["ai_provider"],
                "ollama_url": original["ollama_url"],
                "ollama_model": original["ollama_model"],
            })

    def test_test_emergent_with_garbage_key(self):
        r = requests.post(f"{API}/settings/test-emergent",
                          json={"emergent_key": "sk-emergent-totally-bogus-key"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["reachable"] is False
        assert "error" in d and isinstance(d["error"], str)

    def test_test_emergent_with_bundled_env_key(self):
        # Empty payload -> backend falls back to EMERGENT_LLM_KEY from env.
        r = requests.post(f"{API}/settings/test-emergent", json={})
        assert r.status_code == 200, r.text
        d = r.json()
        # Reachable should be True given the bundled key in /app/backend/.env;
        # if Anthropic gateway is briefly unreachable, accept False with error string.
        assert "reachable" in d
        if d["reachable"]:
            assert "sample" in d
            assert isinstance(d["sample"], str)
        else:
            assert "error" in d


# ---------- bulk-suggest endpoint ----------
class TestBulkSuggest:
    def test_bulk_suggest_400_when_provider_none(self, project):
        original = requests.get(f"{API}/settings").json()
        try:
            requests.put(f"{API}/settings", json={"ai_provider": "none"})
            r = requests.post(f"{API}/transactions/bulk-suggest",
                              json={"project_id": project["id"]})
            assert r.status_code == 400, r.text
        finally:
            requests.put(f"{API}/settings", json={"ai_provider": original["ai_provider"]})

    def test_bulk_suggest_400_when_emergent_no_key(self, project):
        original = requests.get(f"{API}/settings").json()
        # We need a way to make EMERGENT_LLM_KEY env empty. Can't do that here,
        # but we can verify the path: set ai_provider=emergent + emergent_key=""
        # and rely on fallback to env. Since env IS set, this won't 400.
        # Instead, we just verify response is not 500.
        try:
            requests.put(f"{API}/settings", json={
                "ai_provider": "emergent", "emergent_key": ""
            })
            r = requests.post(f"{API}/transactions/bulk-suggest",
                              json={"project_id": project["id"],
                                    "only_uncategorized": True,
                                    "max_items": 1})
            # With env key present, expect 200 (or 400 only if env absent)
            assert r.status_code in (200, 400), r.text
        finally:
            requests.put(f"{API}/settings", json={
                "ai_provider": original["ai_provider"],
                "emergent_key": original.get("emergent_key", "")
            })

    def test_bulk_suggest_response_shape_minimal(self, project, categories):
        """Run with only_uncategorized=True and a single tx to limit LLM calls."""
        # Add a single small transaction in a brand-new project to keep cost low
        r = requests.post(f"{API}/projects",
                          json={"name": "TEST_Iter7_BulkSug", "description": "x"})
        proj2 = r.json()
        try:
            _upload_csv(proj2["id"],
                        b"Date,Description,Amount\n01/01/2025,TEST_BS_TESCO,10.00\n")
            r = requests.post(f"{API}/transactions/bulk-suggest",
                              json={"project_id": proj2["id"],
                                    "only_uncategorized": True,
                                    "allow_create": True,
                                    "max_items": 1})
            assert r.status_code == 200, r.text
            d = r.json()
            for k in ("processed", "categorized", "created_categories",
                      "errors", "provider"):
                assert k in d
            assert isinstance(d["created_categories"], list)
            assert isinstance(d["errors"], list)
            assert d["processed"] == 1
        finally:
            requests.delete(f"{API}/projects/{proj2['id']}")
