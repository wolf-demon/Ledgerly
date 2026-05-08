"""Iteration 6 backend tests: parser improvements, reclassify, settings, AI provider dispatch."""
import os
import sys
import requests
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def project():
    r = requests.post(f"{API}/projects", json={"name": "TEST_Iter6", "description": "iter6"})
    assert r.status_code == 200
    p = r.json()
    yield p
    requests.delete(f"{API}/projects/{p['id']}")


# ---------- Parser unit tests ----------
class TestParserTypeColumn:
    def test_type_column_dr_cr(self):
        from server import parse_csv
        csv = (
            b"Date,Type,Description,Amount\n"
            b"01/03/2025,DEBIT,TESCO,45.20\n"
            b"02/03/2025,CREDIT,SALARY,2500.00\n"
        )
        rows = parse_csv(csv)
        assert len(rows) == 2
        by_desc = {r["description"]: r for r in rows}
        assert by_desc["TESCO"]["amount"] == -45.20
        assert by_desc["SALARY"]["amount"] == 2500.00

    def test_debit_credit_columns_take_precedence(self):
        from server import parse_csv
        csv = (
            b"Date,Description,Amount,Debit,Credit\n"
            b"05/03/2025,SHELL,55.00,55.00,\n"
            b"06/03/2025,REFUND,18.50,,18.50\n"
        )
        rows = parse_csv(csv)
        assert len(rows) == 2
        by_desc = {r["description"]: r for r in rows}
        assert by_desc["SHELL"]["amount"] == -55.00
        assert by_desc["REFUND"]["amount"] == 18.50

    def test_signed_amount_no_regression(self):
        from server import parse_csv
        csv = (
            b"Date,Description,Amount\n"
            b"01/04/2025,FOO,-12.34\n"
            b"02/04/2025,BAR,200.00\n"
        )
        rows = parse_csv(csv)
        assert len(rows) == 2
        amts = sorted([r["amount"] for r in rows])
        assert amts == [-12.34, 200.00]


# ---------- Upload + reclassify integration ----------
class TestReclassify:
    def test_upload_type_csv_yields_correct_signs(self, project):
        csv = (
            b"Date,Type,Description,Amount\n"
            b"01/03/2025,DEBIT,RECLASS_TESCO,45.20\n"
            b"02/03/2025,CREDIT,RECLASS_SALARY,2500.00\n"
        )
        files = {"file": ("a.csv", csv, "text/csv")}
        r = requests.post(f"{API}/transactions/upload",
                          data={"project_id": project["id"]}, files=files)
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 2

        txs = requests.get(f"{API}/transactions",
                           params={"project_id": project["id"]}).json()
        tesco = next(t for t in txs if t["description"] == "RECLASS_TESCO")
        salary = next(t for t in txs if t["description"] == "RECLASS_SALARY")
        assert tesco["amount"] == -45.20 and tesco["type"] == "expense"
        assert salary["amount"] == 2500.00 and salary["type"] == "income"

    def test_reclassify_endpoint_returns_shape(self, project):
        r = requests.post(f"{API}/transactions/reclassify",
                          params={"project_id": project["id"]})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "checked" in data and "fixed" in data
        assert isinstance(data["checked"], int) and isinstance(data["fixed"], int)
        # Already correct from upload above -> fixed should be 0
        assert data["fixed"] == 0
        assert data["checked"] >= 2


# ---------- Settings CRUD ----------
class TestSettings:
    def test_get_default_settings(self):
        r = requests.get(f"{API}/settings")
        assert r.status_code == 200
        d = r.json()
        assert d["ai_provider"] in ("emergent", "ollama", "none")
        assert "ollama_url" in d and "ollama_model" in d

    def test_put_partial_update_persists(self):
        # Save current to restore later
        original = requests.get(f"{API}/settings").json()
        try:
            r = requests.put(f"{API}/settings",
                             json={"ollama_model": "qwen2.5:7b"})
            assert r.status_code == 200
            assert r.json()["ollama_model"] == "qwen2.5:7b"
            # persistence
            r2 = requests.get(f"{API}/settings")
            assert r2.json()["ollama_model"] == "qwen2.5:7b"
            # other fields preserved
            assert r2.json()["ai_provider"] == original["ai_provider"]
        finally:
            requests.put(f"{API}/settings", json=original)

    def test_put_invalid_provider_rejected(self):
        r = requests.put(f"{API}/settings", json={"ai_provider": "bogus"})
        assert r.status_code == 400

    def test_test_ollama_unreachable_graceful(self):
        r = requests.post(f"{API}/settings/test-ollama",
                          json={"ollama_url": "http://localhost:11434"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["reachable"] is False
        assert "error" in d and isinstance(d["error"], str) and len(d["error"]) > 0


# ---------- Suggest dispatch by provider ----------
class TestSuggestDispatch:
    def _set_provider(self, provider, **extra):
        body = {"ai_provider": provider, **extra}
        r = requests.put(f"{API}/settings", json=body)
        assert r.status_code == 200

    def test_suggest_disabled(self, project):
        original = requests.get(f"{API}/settings").json()
        try:
            self._set_provider("none")
            r = requests.post(f"{API}/categorize/suggest",
                              json={"project_id": project["id"],
                                    "description": "TESCO",
                                    "amount": -10})
            assert r.status_code == 200
            d = r.json()
            assert d["suggested_category_id"] is None
            assert "disabled" in (d.get("reason") or "").lower()
        finally:
            requests.put(f"{API}/settings", json=original)

    def test_suggest_ollama_unreachable_graceful(self, project):
        original = requests.get(f"{API}/settings").json()
        try:
            self._set_provider("ollama",
                               ollama_url="http://localhost:11434",
                               ollama_model="llama3.2")
            r = requests.post(f"{API}/categorize/suggest",
                              json={"project_id": project["id"],
                                    "description": "NETFLIX",
                                    "amount": -9.99})
            # Must NOT be 500
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["suggested_category_id"] is None
            assert d.get("provider") == "ollama"
            assert "error" in (d.get("reason") or "").lower() or \
                   "ollama" in (d.get("reason") or "").lower()
        finally:
            requests.put(f"{API}/settings", json=original)

    def test_suggest_emergent_works(self, project):
        original = requests.get(f"{API}/settings").json()
        try:
            self._set_provider("emergent")
            r = requests.post(f"{API}/categorize/suggest",
                              json={"project_id": project["id"],
                                    "description": "TESCO",
                                    "amount": -10})
            assert r.status_code == 200, r.text
            # Either has a real suggestion or a graceful reason; never 500.
            d = r.json()
            assert "suggested_category_id" in d
        finally:
            requests.put(f"{API}/settings", json=original)
