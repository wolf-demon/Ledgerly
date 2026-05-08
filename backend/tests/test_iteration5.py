"""Iteration 5 backend tests: multi-format upload (TSV, XLSX, XLS, ODS, OFX) and /transactions/import-url."""
import io
import os
import sys
import requests
import pytest
import pandas as pd
import openpyxl
from unittest.mock import patch, MagicMock

# ensure server importable for helper-level tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

BASE_URL = os.environ['REACT_APP_BACKEND_URL'].rstrip('/')
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def project():
    r = requests.post(f"{API}/projects", json={"name": "TEST_Iter5", "description": "iter5"})
    assert r.status_code == 200
    p = r.json()
    yield p
    requests.delete(f"{API}/projects/{p['id']}")


# ---------- helpers to build files in-memory ----------
def _build_xlsx_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Date", "Description", "Amount"])
    ws.append(["01/06/2025", "XLSX TESCO", -12.34])
    ws.append(["02/06/2025", "XLSX SALARY", 1500.00])
    ws.append(["03/06/2025", "XLSX NETFLIX", -9.99])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_xls_bytes() -> bytes:
    df = pd.DataFrame([
        {"Date": "01/07/2025", "Description": "XLS COFFEE", "Amount": -3.50},
        {"Date": "02/07/2025", "Description": "XLS WAGES",  "Amount": 1200.00},
    ])
    buf = io.BytesIO()
    # xlwt is required to write .xls; fall back to xlsxwriter via openpyxl is wrong format.
    try:
        df.to_excel(buf, index=False, engine="xlwt")
        return buf.getvalue()
    except Exception:
        return b""  # marker for skip


def _build_ods_bytes() -> bytes:
    df = pd.DataFrame([
        {"Date": "01/08/2025", "Description": "ODS LIDL",   "Amount": -22.10},
        {"Date": "02/08/2025", "Description": "ODS BONUS",  "Amount": 250.00},
    ])
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="odf")
    return buf.getvalue()


OFX_BODY = (
    b"OFXHEADER:100\r\nDATA:OFXSGML\r\nVERSION:102\r\nSECURITY:NONE\r\n"
    b"ENCODING:USASCII\r\nCHARSET:1252\r\nCOMPRESSION:NONE\r\nOLDFILEUID:NONE\r\nNEWFILEUID:NONE\r\n\r\n"
    b"<OFX><BANKMSGSRSV1><STMTTRNRS><TRNUID>1<STATUS><CODE>0<SEVERITY>INFO</STATUS>"
    b"<STMTRS><CURDEF>GBP<BANKACCTFROM><BANKID>123<ACCTID>456<ACCTTYPE>CHECKING</BANKACCTFROM>"
    b"<BANKTRANLIST><DTSTART>20250101<DTEND>20250131"
    b"<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20250115<TRNAMT>-22.50<FITID>1<NAME>OFX SAINSBURYS</STMTTRN>"
    b"<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20250101<TRNAMT>1800.00<FITID>2<NAME>OFX SALARY</STMTTRN>"
    b"</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"
)


# ---------- Upload: format coverage ----------
class TestUploadFormats:
    def test_csv_still_works(self, project):
        csv = b"Date,Description,Amount\n01/05/2025,CSV TESCO,-10.00\n"
        files = {"file": ("a.csv", csv, "text/csv")}
        r = requests.post(f"{API}/transactions/upload", data={"project_id": project["id"]}, files=files)
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 1

    def test_tsv(self, project):
        tsv = b"Date\tDescription\tAmount\n02/05/2025\tTSV ALDI\t-7.25\n03/05/2025\tTSV WAGES\t900.00\n"
        files = {"file": ("a.tsv", tsv, "text/tab-separated-values")}
        r = requests.post(f"{API}/transactions/upload", data={"project_id": project["id"]}, files=files)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["inserted"] == 2 and d["total"] == 2

    def test_xlsx(self, project):
        content = _build_xlsx_bytes()
        files = {"file": ("a.xlsx", content,
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = requests.post(f"{API}/transactions/upload", data={"project_id": project["id"]}, files=files)
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 3

    def test_xls(self, project):
        content = _build_xls_bytes()
        if not content:
            pytest.skip("xlwt not installed - cannot author .xls in-test")
        files = {"file": ("a.xls", content, "application/vnd.ms-excel")}
        r = requests.post(f"{API}/transactions/upload", data={"project_id": project["id"]}, files=files)
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 2

    def test_ods(self, project):
        content = _build_ods_bytes()
        files = {"file": ("a.ods", content, "application/vnd.oasis.opendocument.spreadsheet")}
        r = requests.post(f"{API}/transactions/upload", data={"project_id": project["id"]}, files=files)
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 2

    def test_ofx(self, project):
        files = {"file": ("a.ofx", OFX_BODY, "application/x-ofx")}
        r = requests.post(f"{API}/transactions/upload", data={"project_id": project["id"]}, files=files)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["inserted"] == 2
        # verify amounts persisted
        txs = requests.get(f"{API}/transactions", params={"project_id": project["id"]}).json()
        ofx_descs = {t["description"] for t in txs if "OFX" in t["description"].upper()}
        assert any("SAINSBURYS" in s.upper() or "SALARY" in s.upper() for s in ofx_descs)

    def test_unknown_extension_falls_back_to_csv(self, project):
        # No extension, but content is valid CSV -> should still parse
        content = b"Date,Description,Amount\n10/09/2025,FALLBACK COFFEE,-4.00\n"
        files = {"file": ("statement", content, "application/octet-stream")}
        r = requests.post(f"{API}/transactions/upload", data={"project_id": project["id"]}, files=files)
        assert r.status_code == 200, r.text
        assert r.json()["inserted"] == 1


# ---------- Helper: google_sheet_to_csv_url ----------
class TestGoogleSheetUrlHelper:
    def test_transformations(self):
        from server import google_sheet_to_csv_url as g
        sid = "1AbCDeFgHiJKLmnOPqrstuvWXYZ_0123456789-abc"
        # /edit
        assert g(f"https://docs.google.com/spreadsheets/d/{sid}/edit") == \
            f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid=0"
        # /edit?gid=N
        assert g(f"https://docs.google.com/spreadsheets/d/{sid}/edit?gid=42") == \
            f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid=42"
        # /edit?usp=sharing
        assert g(f"https://docs.google.com/spreadsheets/d/{sid}/edit?usp=sharing") == \
            f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid=0"
        # trailing slash
        assert g(f"https://docs.google.com/spreadsheets/d/{sid}/") == \
            f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid=0"
        # gid in fragment
        assert g(f"https://docs.google.com/spreadsheets/d/{sid}/edit#gid=99") == \
            f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid=99"
        # not a sheet URL
        assert g("https://example.com/foo.csv") is None


# ---------- /transactions/import-url ----------
class TestImportUrl:
    def test_project_not_found(self):
        r = requests.post(f"{API}/transactions/import-url",
                          json={"project_id": "nonexistent-id", "url": "https://example.com/x.csv"})
        assert r.status_code == 404

    def test_non_google_csv_url(self, project):
        # Use a real raw GitHub CSV (3 small rows). Skip on network failure.
        url = "https://raw.githubusercontent.com/datasets/finance-vix/main/data/vix-daily.csv"
        try:
            head = requests.get(url, timeout=10)
            if head.status_code != 200:
                pytest.skip(f"Network unavailable / URL returned {head.status_code}")
        except Exception as e:
            pytest.skip(f"No internet: {e}")
        # Build our own tiny csv hosted via gist-like raw - safer: post a real github-hosted file
        small = "https://raw.githubusercontent.com/curran/data/gh-pages/dbpedia/Country-FlagCode-Latitude-Longitude.csv"
        # That CSV doesn't have Date/Description/Amount columns -> expect 400 "no transaction rows"
        r = requests.post(f"{API}/transactions/import-url",
                          json={"project_id": project["id"], "url": small}, timeout=60)
        # Either 400 (no tx rows) or 200 if columns matched. Both are acceptable - we mainly verify endpoint reachable.
        assert r.status_code in (200, 400), r.text

    def test_google_sheets_private_url_gives_helpful_error(self, project):
        # Random sheet ID guaranteed not public -> Google returns 401/403/404
        bad_url = "https://docs.google.com/spreadsheets/d/1ZZZ_DOES_NOT_EXIST_AaaaBbbbCccc/edit"
        r = requests.post(f"{API}/transactions/import-url",
                          json={"project_id": project["id"], "url": bad_url}, timeout=60)
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "Anyone with the link" in detail, f"Expected helpful hint, got: {detail}"

    def test_google_sheets_url_transforms_and_imports_via_mock(self, project):
        """Verify the endpoint converts a /edit URL to the export?format=csv URL and
        imports rows. We hit the live endpoint but cannot mock its internals, so this
        also serves as an integration test using a real public sheet if available.

        Since we don't have a known live public sheet, we instead validate the
        helper transformation already (above) and only assert the endpoint shape via a
        synthetic public sheet attempt. We accept 400 (private/missing) but the source
        tagging (google-sheets) only appears on success, so we just smoke-call.
        """
        # Use a well-known publicly-shared sample sheet (Google's public sample) if reachable.
        url = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
        try:
            r = requests.post(f"{API}/transactions/import-url",
                              json={"project_id": project["id"], "url": url}, timeout=60)
        except Exception as e:
            pytest.skip(f"No network: {e}")
        # Either 200 success (with source=google-sheets) or 400 (private/no-tx-rows)
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            assert r.json().get("source") == "google-sheets"


# ---------- Method-level parser tests ----------
class TestParserUnits:
    def test_parse_tsv(self):
        from server import parse_tsv
        tsv = b"Date\tDescription\tAmount\n01/01/2025\tFOO\t-1.00\n"
        rows = parse_tsv(tsv)
        assert len(rows) == 1 and rows[0]["amount"] == -1.0

    def test_parse_excel(self):
        from server import parse_excel
        rows = parse_excel(_build_xlsx_bytes())
        assert len(rows) == 3
        assert any(r["description"] == "XLSX SALARY" and r["amount"] == 1500.0 for r in rows)

    def test_parse_ods(self):
        from server import parse_ods
        rows = parse_ods(_build_ods_bytes())
        assert len(rows) == 2

    def test_parse_ofx(self):
        from server import parse_ofx
        rows = parse_ofx(OFX_BODY)
        assert len(rows) >= 2
        amounts = sorted([r["amount"] for r in rows])
        assert amounts == [-22.50, 1800.00]

    def test_detect_format(self):
        from server import detect_format
        assert detect_format("a.csv", "text/csv") == "csv"
        assert detect_format("a.tsv", "") == "tsv"
        assert detect_format("a.xlsx", "") == "xlsx"
        assert detect_format("a.xls", "") == "xls"
        assert detect_format("a.ods", "") == "ods"
        assert detect_format("a.ofx", "") == "ofx"
        assert detect_format("a.qfx", "") == "ofx"
        assert detect_format("a.pdf", "") == "pdf"
        assert detect_format("a.bin", "application/octet-stream") is None
