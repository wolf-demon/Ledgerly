"""File parsers for bank statements: CSV, TSV, Excel (xlsx/xls), ODS, OFX, PDF, Google Sheets URL."""
import io
import re
from typing import Any, Dict, List, Optional

import pandas as pd
import pdfplumber

from .helpers import find_column, parse_amount, parse_date


def _parse_dataframe(df: "pd.DataFrame") -> List[Dict[str, Any]]:
    """Shared row-extraction logic for CSV / TSV / Excel / ODS dataframes."""
    cols = list(df.columns)
    date_col = find_column(cols, ['date', 'posted', 'transaction date'])
    desc_col = find_column(cols, ['description', 'detail', 'narrative', 'memo', 'particulars', 'reference', 'payee', 'name'])
    amount_col = find_column(cols, ['amount', 'value'])
    debit_col = find_column(cols, ['debit', 'paid out', 'withdrawal', 'money out', 'out'])
    credit_col = find_column(cols, ['credit', 'paid in', 'deposit', 'money in', 'in'])
    type_col = find_column(cols, ['dr/cr', 'cr/dr', 'transaction type', 'txn type', 'type'])

    # Avoid type_col matching the description column when banks use a column literally named "Type"
    if type_col == desc_col:
        type_col = None

    DEBIT_HINTS = {"DR", "DEBIT", "D", "OUT", "PAYMENT", "WITHDRAWAL", "PURCHASE", "POS", "ATM"}
    CREDIT_HINTS = {"CR", "CREDIT", "C", "IN", "DEPOSIT", "REFUND", "TRANSFER IN"}

    rows = []
    for _, r in df.iterrows():
        date_val = parse_date(r[date_col]) if date_col else None
        desc_val = str(r[desc_col]).strip() if desc_col and pd.notna(r[desc_col]) else ''
        amt: Optional[float] = None

        if debit_col or credit_col:
            d = parse_amount(r[debit_col]) if debit_col else None
            c = parse_amount(r[credit_col]) if credit_col else None
            if d is not None and d != 0:
                amt = -abs(d)
            elif c is not None and c != 0:
                amt = abs(c)

        if amt is None and amount_col:
            raw = parse_amount(r[amount_col])
            if raw is not None:
                if type_col:
                    type_val = str(r[type_col] or '').strip().upper()
                    type_token = next((tok for tok in type_val.split() if tok in DEBIT_HINTS or tok in CREDIT_HINTS), type_val)
                    if type_token in DEBIT_HINTS:
                        amt = -abs(raw)
                    elif type_token in CREDIT_HINTS:
                        amt = abs(raw)
                    else:
                        amt = raw
                else:
                    amt = raw

        if not date_val or not desc_val or amt is None:
            continue
        rows.append({"date": date_val, "description": desc_val, "amount": amt})
    return rows


def parse_csv(content: bytes, sep: str = ",") -> List[Dict[str, Any]]:
    try:
        df = pd.read_csv(io.BytesIO(content), sep=sep)
    except Exception:
        df = pd.read_csv(io.BytesIO(content), sep=sep, encoding='latin-1')
    return _parse_dataframe(df)


def parse_tsv(content: bytes) -> List[Dict[str, Any]]:
    return parse_csv(content, sep="\t")


def parse_excel(content: bytes) -> List[Dict[str, Any]]:
    last_err = None
    for engine in ("openpyxl", "xlrd"):
        try:
            sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, engine=engine)
            for _, df in sheets.items():
                rows = _parse_dataframe(df)
                if rows:
                    return rows
            return []
        except Exception as e:
            last_err = e
            continue
    raise ValueError(f"Could not read Excel file: {last_err}")


def parse_ods(content: bytes) -> List[Dict[str, Any]]:
    sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, engine="odf")
    for _, df in sheets.items():
        rows = _parse_dataframe(df)
        if rows:
            return rows
    return []


def parse_ofx(content: bytes) -> List[Dict[str, Any]]:
    from ofxparse import OfxParser
    ofx = OfxParser.parse(io.BytesIO(content))
    rows = []
    for acct in getattr(ofx, "accounts", []) or []:
        statement = getattr(acct, "statement", None)
        if not statement:
            continue
        for tx in getattr(statement, "transactions", []) or []:
            try:
                date_val = tx.date.strftime("%Y-%m-%d") if tx.date else None
                amt = float(tx.amount) if tx.amount is not None else None
                desc = (getattr(tx, "memo", "") or getattr(tx, "payee", "") or "").strip()
                if date_val and desc and amt is not None:
                    rows.append({"date": date_val, "description": desc, "amount": amt})
            except Exception:
                continue
    return rows


def parse_pdf(content: bytes) -> List[Dict[str, Any]]:
    rows = []
    text_blocks = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            try:
                tables = page.extract_tables()
                for tbl in tables:
                    if not tbl or len(tbl) < 2:
                        continue
                    header = [str(h or '').lower() for h in tbl[0]]
                    date_idx = next((i for i, h in enumerate(header) if 'date' in h), None)
                    desc_idx = next((i for i, h in enumerate(header) if any(k in h for k in ['descr', 'detail', 'narr', 'partic'])), None)
                    amt_idx = next((i for i, h in enumerate(header) if 'amount' in h), None)
                    debit_idx = next((i for i, h in enumerate(header) if 'debit' in h or 'paid out' in h or 'withdraw' in h), None)
                    credit_idx = next((i for i, h in enumerate(header) if 'credit' in h or 'paid in' in h or 'deposit' in h), None)
                    for r in tbl[1:]:
                        if not r:
                            continue
                        d = parse_date(r[date_idx]) if date_idx is not None and date_idx < len(r) else None
                        desc = str(r[desc_idx]).strip() if desc_idx is not None and desc_idx < len(r) and r[desc_idx] else ''
                        amt = None
                        if amt_idx is not None and amt_idx < len(r):
                            amt = parse_amount(r[amt_idx])
                        if amt is None:
                            di = parse_amount(r[debit_idx]) if debit_idx is not None and debit_idx < len(r) else None
                            ci = parse_amount(r[credit_idx]) if credit_idx is not None and credit_idx < len(r) else None
                            if di is not None and di != 0:
                                amt = -abs(di)
                            elif ci is not None and ci != 0:
                                amt = abs(ci)
                        if d and desc and amt is not None:
                            rows.append({"date": d, "description": desc, "amount": amt})
            except Exception:
                pass
            try:
                text_blocks.append(page.extract_text() or '')
            except Exception:
                pass

    if rows:
        return rows

    text = "\n".join(text_blocks)
    pattern = re.compile(
        r'(\d{1,2}[\/\-\s][A-Za-z\d]{1,4}[\/\-\s]\d{2,4})\s+(.+?)\s+(-?£?\(?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?)',
    )
    for m in pattern.finditer(text):
        d = parse_date(m.group(1))
        desc = m.group(2).strip()
        amt = parse_amount(m.group(3))
        if d and desc and amt is not None:
            rows.append({"date": d, "description": desc, "amount": amt})
    return rows


def google_sheet_to_csv_url(url: str) -> Optional[str]:
    """Convert any public Google Sheets share URL into its CSV export URL."""
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not m:
        return None
    sheet_id = m.group(1)
    gid_m = re.search(r"[?&#]gid=(\d+)", url)
    gid = gid_m.group(1) if gid_m else "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


_PARSERS: Dict[str, Any] = {
    "csv": parse_csv,
    "tsv": parse_tsv,
    "pdf": parse_pdf,
    "xlsx": parse_excel,
    "xls": parse_excel,
    "ods": parse_ods,
    "ofx": parse_ofx,
    "qfx": parse_ofx,
}


def detect_format(filename: str, content_type: Optional[str]) -> Optional[str]:
    name = (filename or "").lower()
    ct = (content_type or "").lower()
    if name.endswith(".csv") or ct == "text/csv":
        return "csv"
    if name.endswith(".tsv") or ct in ("text/tab-separated-values", "text/tsv"):
        return "tsv"
    if name.endswith(".pdf") or ct == "application/pdf":
        return "pdf"
    if name.endswith(".xlsx") or "spreadsheetml" in ct:
        return "xlsx"
    if name.endswith(".xls") or ct == "application/vnd.ms-excel":
        return "xls"
    if name.endswith(".ods") or "opendocument.spreadsheet" in ct:
        return "ods"
    if name.endswith(".ofx") or name.endswith(".qfx") or "ofx" in ct:
        return "ofx"
    return None


def parse_any(content: bytes, filename: str, content_type: Optional[str]) -> List[Dict[str, Any]]:
    """Dispatch to the right parser, with sensible fallback chain."""
    fmt = detect_format(filename, content_type)
    parser = _PARSERS.get(fmt) if fmt else None
    if parser is not None:
        return parser(content)
    try:
        rows = parse_csv(content)
        if rows:
            return rows
    except Exception:
        pass
    try:
        return parse_pdf(content)
    except Exception:
        return []
