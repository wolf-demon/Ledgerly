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


_MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"


def _infer_year(text: str) -> Optional[int]:
    """Find the year a statement covers — try multiple statement header patterns."""
    # "Statementdate: 04 March 2026" / "Statement date 04 March 2026"
    m = re.search(r"[Ss]tatement\s*date[: ]+\d{1,2}\s+\w+\s+(20\d{2})", text)
    if m:
        return int(m.group(1))
    # "01 January 2026 to 31 January 2026" (BoS-style period header)
    m = re.search(r"\b\d{1,2}\s+\w+\s+(20\d{2})\s+to\s+\d{1,2}\s+\w+\s+\d{4}", text)
    if m:
        return int(m.group(1))
    # "Balance from statement X dated DD/MM/YYYY"
    m = re.search(r"dated\s+\d{1,2}[/.-]\d{1,2}[/.-](20\d{2})", text)
    if m:
        return int(m.group(1))
    # Anywhere standalone "2026" reasonably close to a "Statement" word
    m = re.search(r"[Ss]tatement[^\n]{0,80}(20\d{2})", text)
    if m:
        return int(m.group(1))
    return None


def _parse_pdf_tables_with_continuation(pdf, default_year: Optional[int]) -> List[Dict[str, Any]]:
    """Walk every table on every page, merging continuation rows (empty date,
    extra description fragment) into the preceding transaction.

    Required for banks like Nationwide which split each transaction across
    2-4 lines in their table layout. Banks often also split a single logical
    table into several pdfplumber tables on the same page — when a follow-up
    table has no recognizable header we inherit the previous one's column
    indices.
    """
    rows: List[Dict[str, Any]] = []
    for page in pdf.pages:
        try:
            tables = page.extract_tables()
        except Exception:
            continue

        # State carried between tables on the SAME page so headerless
        # continuation-tables can reuse the previous schema.
        page_idx: Dict[str, Optional[int]] = {"date": None, "desc": None, "amt": None, "out": None, "in_": None}

        for tbl in tables:
            if not tbl:
                continue
            header = [str(h or '').lower() for h in tbl[0]]
            has_header = any('date' in h for h in header) and any(
                any(k in h for k in ['descr', 'detail', 'narr', 'partic']) for h in header
            )

            data_start = 0
            if has_header:
                page_idx["date"] = next((i for i, h in enumerate(header) if 'date' in h), None)
                page_idx["desc"] = next((i for i, h in enumerate(header) if any(k in h for k in ['descr', 'detail', 'narr', 'partic'])), None)
                page_idx["amt"] = next((i for i, h in enumerate(header) if h.strip() == 'amount' or h.endswith(' amount')), None)
                page_idx["out"] = next((i for i, h in enumerate(header) if any(k in h for k in ['out', 'debit', 'withdraw']) and 'balance' not in h), None)
                page_idx["in_"] = next(
                    (i for i, h in enumerate(header) if any(k in h for k in ['in', 'credit', 'deposit']) and 'balance' not in h and i != page_idx["out"]),
                    None,
                )
                data_start = 1

            date_idx = page_idx["date"]
            desc_idx = page_idx["desc"]
            amt_idx = page_idx["amt"]
            out_idx = page_idx["out"]
            in_idx = page_idx["in_"]
            if date_idx is None or desc_idx is None:
                continue

            current: Optional[Dict[str, Any]] = None

            def _flush():
                nonlocal current
                if current and current.get("amount") is not None and current.get("date") and current.get("description"):
                    current["description"] = re.sub(r"\s+", " ", current["description"]).strip()
                    rows.append(current)
                current = None

            for r in tbl[data_start:]:
                if not r:
                    continue
                date_cell = str(r[date_idx] or '').strip() if date_idx < len(r) else ''
                desc_cell = str(r[desc_idx] or '').strip() if desc_idx < len(r) else ''

                # Header/balance noise rows: "2026 Balance from statement ..." etc.
                if re.fullmatch(r"20\d{2}\s+[\d,]+\.\d{2}", date_cell) or "balance from" in (date_cell + " " + desc_cell).lower():
                    yr = re.search(r"(20\d{2})", date_cell)
                    if yr:
                        default_year = int(yr.group(1))
                    continue

                amt = None
                if amt_idx is not None and amt_idx < len(r):
                    amt = parse_amount(r[amt_idx])
                if amt is None:
                    di = parse_amount(r[out_idx]) if out_idx is not None and out_idx < len(r) else None
                    ci = parse_amount(r[in_idx]) if in_idx is not None and in_idx < len(r) else None
                    if di is not None and di != 0:
                        amt = -abs(di)
                    elif ci is not None and ci != 0:
                        amt = abs(ci)

                if date_cell and amt is not None:
                    _flush()
                    d = None
                    if re.search(r"\b\d{4}\b", date_cell):
                        d = parse_date(date_cell)
                    elif default_year:
                        d = parse_date(f"{date_cell} {default_year}")
                    else:
                        d = parse_date(date_cell)
                    current = {"date": d, "description": desc_cell, "amount": amt}
                elif date_cell and amt is None:
                    # Date-only row (e.g. group separator) — flush any in-progress tx.
                    _flush()
                elif amt is not None and current and not date_cell:
                    inherited_date = current["date"]
                    _flush()
                    current = {"date": inherited_date, "description": desc_cell, "amount": amt}
                elif desc_cell and current:
                    current["description"] = (current["description"] + " " + desc_cell).strip()

            _flush()
    return rows


_CREDIT_HINTS = (
    "bank credit", "credit ", "refund", "transfer from", "salary", "wages",
    "payment from", "received from", "interest credit", "deposit",
)
_DEBIT_HINTS = (
    "direct debit", "transfer to", "payment to", "contactless", "standing order",
    "cash withdrawal", "card payment", "atm",
)
_TX_LINE_RE = re.compile(
    r"^\s*(?:(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))\s+)?"  # optional leading date
    r"(.+?)"
    r"\s+(\d{1,3}(?:,\d{3})*\.\d{2})"                  # amount
    r"(?:\s+(\d{1,3}(?:,\d{3})*\.\d{2}))?"             # optional balance after amount
    r"(?:\s+.+)?\s*$",                                  # trailing junk allowed (e.g. "Statementdate ...")
    re.IGNORECASE,
)
_DATE_ONLY_RE = re.compile(
    r"^\s*(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))\s*$",
    re.IGNORECASE,
)
_NOISE_PREFIXES = (
    "statement", "sortcode", "sort code", "account", "head office", "tel ",
    "your ", "nationwide", "balance from", "effective date", "averagecredit",
    "averagedebit", "receivingan", "internationalpayment", "intermediarybank",
    "bic ", "iban ", "swift",
)


_BOS_ROW = re.compile(
    # Bank-of-Scotland-style malformed PDF where column headers leak into data.
    # The first DIGIT of the day and first LETTER of the description / type
    # cells get prepended into the column header text — we capture both so we
    # can put them back where they belong. Pattern:
    #   D{day_first_digit}ate <rest_of_day> <Mon> <YY>
    #   D{desc_first_char}escription <rest_of_desc>
    #   T{type_first_char}ype <rest_of_type>
    #   <amt> Money Out (£) <bal> Balance (£)   OR
    #   <amt> Money In (£)   Money Obulat n(£k). <bal> Balance (£)
    r"D([A-Za-z0-9])ate\s+(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{2})"
    r"\s+D([A-Za-z])escription\s+(.+?)"
    r"\s+T[A-Za-z]?ype\s+\S+\s+"
    r"(?:"
        r"Moneyb?\s*Ilna\s*n?\s*\(?k?£?\.?\)?\s*([\d,]+\.\d{2})\s*Money\s*Out\s*\(£\)"
        r"|"
        r"([\d,]+\.\d{2})\s*Money\s*In\s*\(£\)"
    r")",
    re.IGNORECASE,
)


def _parse_bos_text(text: str) -> List[Dict[str, Any]]:
    """Parse Bank of Scotland's mangled extract_text() output.

    The PDF's text layer interleaves header chars with cell values so that the
    first character of each cell ends up *inside* the column header. We capture
    those characters via the regex and reconstruct the true values.
    """
    rows: List[Dict[str, Any]] = []
    for m in _BOS_ROW.finditer(text):
        date_lead, date_rest, desc_lead, desc_rest, money_out, money_in = m.groups()
        date_str = f"{date_lead}{date_rest}"        # "0" + "2 Jan 26"  -> "02 Jan 26"
        # The first letter of the description leaks into the column header.
        # Sometimes the leaked letter is the SAME as the description's actual
        # first letter (e.g. "DPescription POINT_*KENILWORTH" -> lead="P",
        # rest="POINT..."); in that case we'd produce "PPOINT" by naive
        # concatenation. Only prepend the lead character when it isn't already
        # at the start of the rest.
        if desc_rest and desc_lead.upper() == desc_rest[0].upper():
            desc = desc_rest
        else:
            desc = f"{desc_lead}{desc_rest}"
        desc = re.sub(r"\s+", " ", desc).strip()
        try:
            dt = pd.to_datetime(date_str, format='%d %b %y', errors='coerce')
            if pd.isna(dt):
                continue
            iso = dt.strftime('%Y-%m-%d')
        except Exception:
            continue
        if money_out:
            amount = -float(money_out.replace(',', ''))
        elif money_in:
            amount = float(money_in.replace(',', ''))
        else:
            continue
        if not desc:
            continue
        rows.append({"date": iso, "description": desc, "amount": amount})
    return rows


def _looks_like_noise(line: str) -> bool:
    lower = line.lower().strip()
    if not lower:
        return True
    return any(lower.startswith(p) for p in _NOISE_PREFIXES)


def _infer_sign(description: str, amount: float) -> float:
    """Determine if a text-extracted line is income (positive) or expense (negative)."""
    lower = description.lower()
    if any(h in lower for h in _DEBIT_HINTS):
        return -abs(amount)
    if any(h in lower for h in _CREDIT_HINTS):
        return abs(amount)
    return -abs(amount)  # default: most rows in a personal statement are expenses


def _parse_pdf_text_lines(text: str, default_year: Optional[int]) -> List[Dict[str, Any]]:
    """Last-mile fallback: walk the joined page text line-by-line.

    A transaction line ends with an amount (and optionally a running balance).
    The date may be at the start of the line OR inherited from the most recent
    date-bearing line above.
    """
    rows: List[Dict[str, Any]] = []
    last_date_str: Optional[str] = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line or _looks_like_noise(line):
            continue

        # Pure "DD Mon" header line — just updates the carried date.
        date_only = _DATE_ONLY_RE.match(line)
        if date_only:
            last_date_str = date_only.group(1)
            continue

        m = _TX_LINE_RE.match(line)
        if not m:
            continue

        date_str = m.group(1) or last_date_str
        desc = m.group(2).strip()
        amount_str = m.group(3)
        # If a 2nd number is present (balance), trust it implicitly — keep amount.

        if not date_str:
            continue
        # Filter out short / junk descriptions that the line regex sometimes
        # picks up from things like fee schedules or balance-carried-forward rows.
        if len(desc) < 3 or desc.lower().startswith(("effective date", "sort code", "account number")):
            continue
        if re.fullmatch(r"\d{2,4}", desc):
            # Pure-numeric description like "2026" — that's a balance row, not a transaction.
            continue

        try:
            amount = float(amount_str.replace(",", ""))
        except Exception:
            continue
        amount = _infer_sign(desc, amount)

        # Resolve to ISO date.
        if default_year:
            d = parse_date(f"{date_str} {default_year}")
        else:
            d = parse_date(date_str)
        if not d:
            continue

        rows.append({"date": d, "description": desc, "amount": amount})
        last_date_str = date_str

    return rows


def _dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop rows that share the same (date, amount) AND have substantially
    overlapping descriptions. We prefer the LONGER description (tables tend to
    give us more detail than the line fallback)."""
    out: List[Dict[str, Any]] = []
    for r in rows:
        match_idx = None
        for i, existing in enumerate(out):
            if existing["date"] != r["date"]:
                continue
            if abs(float(existing["amount"]) - float(r["amount"])) > 0.001:
                continue
            d1 = existing["description"].lower()
            d2 = r["description"].lower()
            if d1 in d2 or d2 in d1 or d1.split()[0] == d2.split()[0]:
                match_idx = i
                break
        if match_idx is None:
            out.append(r)
        elif len(r["description"]) > len(out[match_idx]["description"]):
            out[match_idx] = r
    return out


def parse_pdf(content: bytes) -> List[Dict[str, Any]]:
    table_rows: List[Dict[str, Any]] = []
    text_rows: List[Dict[str, Any]] = []
    bos_rows: List[Dict[str, Any]] = []

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        full_text = "".join((p.extract_text() or "") + "\n" for p in pdf.pages)
        default_year = _infer_year(full_text)

        # 1. Structured tables (handles continuation rows + header inheritance).
        table_rows = _parse_pdf_tables_with_continuation(pdf, default_year)

        # 2. Specialised Bank of Scotland regex over the broken text layer.
        bos_rows = _parse_bos_text(full_text)

        # 3. Generic UK-bank line-by-line text fallback — catches the rows that
        #    extract_tables() missed entirely (Nationwide does this for some
        #    transactions that fall on page-section boundaries).
        text_rows = _parse_pdf_text_lines(full_text, default_year)

    # Prefer table data (more reliable in/out), but include text rows for any
    # (date, amount) the tables missed. BoS rows only apply when tables yield
    # nothing on a typically-broken statement.
    combined: List[Dict[str, Any]] = []
    if table_rows:
        combined = list(table_rows)
        combined.extend(text_rows)
        combined = _dedupe_rows(combined)
    elif bos_rows:
        combined = bos_rows
    else:
        combined = text_rows

    if combined:
        return combined

    # Absolute last-resort generic regex.
    pattern = re.compile(
        r'(\d{1,2}[\/\-\s][A-Za-z\d]{1,4}[\/\-\s]\d{2,4})\s+(.+?)\s+(-?£?\(?\d{1,3}(?:,\d{3})*(?:\.\d{2})?\)?)',
    )
    rows: List[Dict[str, Any]] = []
    for m in pattern.finditer(full_text):
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
