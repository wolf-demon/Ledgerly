"""Iteration 10 — real-world PDF parsing regression tests.

Two challenging UK bank PDF formats are pinned here so that future parser
changes can never silently regress them:

  * Nationwide FlexBasic — clean tables with multi-row transactions and the
    same logical table split into multiple pdfplumber tables on one page.
  * Bank of Scotland — broken text layer where every column header has the
    first character of the next cell interleaved into it.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.parsers import parse_pdf  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> bytes:
    with open(FIXTURES / name, "rb") as fh:
        return fh.read()


# ─── Nationwide ─────────────────────────────────────────────────────────────

def test_nationwide_row_count():
    rows = parse_pdf(_load("nationwide_mar2026.pdf"))
    # 20 transactions across the statement period; we accept ±1 in case
    # pdfplumber's table detection drifts slightly between releases.
    assert 19 <= len(rows) <= 21, f"expected ~20 rows, got {len(rows)}"


def test_nationwide_net_matches_balance_delta():
    """Start £1,007.05, end £505.49 → net should be -£501.56."""
    rows = parse_pdf(_load("nationwide_mar2026.pdf"))
    net = sum(r["amount"] for r in rows)
    assert abs(net - (-501.56)) < 0.50, f"net was {net:.2f}, expected ~-501.56"


def test_nationwide_picks_up_largest_expense():
    """The £698 payment to DJ ALEXANDER is on page 2 with trailing junk on
    the same line — easy to miss."""
    rows = parse_pdf(_load("nationwide_mar2026.pdf"))
    dj = next((r for r in rows if "DJ ALEXANDER" in r["description"]), None)
    assert dj is not None, "DJ ALEXANDER row missing"
    assert abs(dj["amount"] - (-698.00)) < 0.01
    assert dj["date"] == "2026-03-02"


def test_nationwide_income_rows_have_positive_amounts():
    rows = parse_pdf(_load("nationwide_mar2026.pdf"))
    credits = [r for r in rows if "Bank credit" in r["description"]]
    assert len(credits) >= 2
    for c in credits:
        assert c["amount"] > 0, f"Bank credit should be positive: {c}"


# ─── Bank of Scotland (broken text layer) ───────────────────────────────────

def test_bos_row_count():
    rows = parse_pdf(_load("bos_jan2026.pdf"))
    assert len(rows) >= 60, f"expected >=60 rows from BoS statement, got {len(rows)}"


def test_bos_descriptions_have_first_letter():
    """The mangled column headers used to swallow the first character of every
    cell (resulting in 'SDA STORES' / 'ESCO STORES'). Make sure we never
    regress."""
    rows = parse_pdf(_load("bos_jan2026.pdf"))
    descs = " | ".join(r["description"].upper() for r in rows)
    # Spot-check a handful of merchants we expect to see in full.
    assert "ASDA STORES" in descs
    assert "TESCO STORES" in descs
    assert "VANQUIS BANK" in descs
    assert "DAILY OD INT" in descs
    assert "MARKS&SPENCER" in descs


def test_bos_no_doubled_first_letter():
    """The 'P' + 'POINT_*KENILWORTH' path used to produce 'PPOINT'. After the
    de-dup fix the description should appear with a single leading 'P'."""
    rows = parse_pdf(_load("bos_jan2026.pdf"))
    descs = [r["description"].upper() for r in rows]
    assert not any(d.startswith("PPOINT") for d in descs), descs


def test_bos_money_in_vs_out_signs():
    rows = parse_pdf(_load("bos_jan2026.pdf"))
    # 'FUTURESE LTD' is a salary credit of ~£1,902.90 → should be positive.
    fut = next((r for r in rows if "FUTURESE" in r["description"].upper()), None)
    assert fut is not None
    assert fut["amount"] > 0, f"FUTURESE LTD should be income, got {fut['amount']}"
    # 'CAPITAL ONE' is a card payment out — negative.
    cap = next((r for r in rows if "CAPITAL ONE" in r["description"].upper()), None)
    assert cap is not None
    assert cap["amount"] < 0, f"CAPITAL ONE should be expense, got {cap['amount']}"


def test_bos_dates_decoded_with_day_prefix():
    """The first digit of the day character used to be lost (parsed '12' as
    '02'). Verify we see dates across multiple distinct days."""
    rows = parse_pdf(_load("bos_jan2026.pdf"))
    days = {r["date"][8:] for r in rows}
    # The statement covers Jan 02 to Jan 30 — expect 10+ distinct days.
    assert len(days) >= 10, f"too few distinct days: {days}"
    assert "30" in days  # the big salary-day
