"""Tests for CSV parsers."""

import os
import tempfile
import textwrap
from datetime import date

import pytest

from revolut_tax_fr.parser import _parse_amount, parse_activity, parse_tax_doc

# ---------------------------------------------------------------------------
# _parse_amount helpers
# ---------------------------------------------------------------------------


def test_parse_amount_eur_prefix():
    assert _parse_amount("€1.23") == pytest.approx(1.23)


def test_parse_amount_dollar_zero():
    assert _parse_amount("$0") == pytest.approx(0.0)


def test_parse_amount_plain():
    assert _parse_amount("19.50") == pytest.approx(19.50)


def test_parse_amount_empty():
    assert _parse_amount("") == pytest.approx(0.0)


def test_parse_amount_none():
    assert _parse_amount(None) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Activity statement parsing
# ---------------------------------------------------------------------------

# Fictional ticker/price/date data — no connection to any real portfolio
_ACTIVITY_CSV = textwrap.dedent("""\
    Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate
    2020-01-15T10:00:00.000Z,FOO,BUY - MARKET,2,USD 50.00,USD 100.00,USD,1.20
    2022-09-30T10:00:00.000Z,FOO,SELL - MARKET,2,USD 60.00,USD 120.00,USD,1.20
    2021-06-01T10:00:00.000Z,BAR,DIVIDEND,,,USD 0.50,USD,1.10
    2021-03-01T12:00:00.000Z,BAZ,DIVIDEND,,,EUR 0.75,EUR,1.0000
    2020-09-01T09:00:00.000Z,,CUSTODY FEE,,,USD -0.08,USD,1.10
""")


def _write_temp(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
    return path


def test_parse_activity_row_count():
    path = _write_temp(_ACTIVITY_CSV)
    rows = parse_activity(path)
    os.unlink(path)
    assert len(rows) == 5


def test_parse_activity_sorted_by_date():
    path = _write_temp(_ACTIVITY_CSV)
    rows = parse_activity(path)
    os.unlink(path)
    dates = [r.date for r in rows]
    assert dates == sorted(dates)


def test_parse_activity_buy_row():
    path = _write_temp(_ACTIVITY_CSV)
    rows = parse_activity(path)
    os.unlink(path)
    buy = next(r for r in rows if r.ticker == "FOO" and r.type == "BUY - MARKET")
    assert buy.quantity == pytest.approx(2.0)
    assert buy.price_per_share == pytest.approx(50.00)
    assert buy.total_amount == pytest.approx(100.00)
    assert buy.fx_rate == pytest.approx(1.20)
    assert buy.currency == "USD"


def test_parse_activity_eur_row():
    """EUR-denominated rows keep fx_rate = 1.0 and have no currency prefix in amount."""
    path = _write_temp(_ACTIVITY_CSV)
    rows = parse_activity(path)
    os.unlink(path)
    baz = next(r for r in rows if r.ticker == "BAZ")
    assert baz.total_amount == pytest.approx(0.75)
    assert baz.fx_rate == pytest.approx(1.0)
    assert baz.currency == "EUR"


def test_parse_activity_no_ticker_row():
    """CUSTODY FEE has no ticker."""
    path = _write_temp(_ACTIVITY_CSV)
    rows = parse_activity(path)
    os.unlink(path)
    fee = next(r for r in rows if r.type == "CUSTODY FEE")
    assert fee.ticker is None
    assert fee.total_amount == pytest.approx(-0.08)


# ---------------------------------------------------------------------------
# Tax document parsing — fictional company/ISIN/price data
# ---------------------------------------------------------------------------

_TAX_DOC_CSV = textwrap.dedent("""\
    Income from Sells
    Date acquired,Date sold,Symbol,Security name,ISIN,Country,Quantity,Cost basis,Gross proceeds,Gross PnL,Currency
    2020-01-15,2022-09-30,FOO,Example Corp,US0000000001,US,2,100.00,120.00,20.00,USD

    Other income & fees
    Date,Symbol,Security name,ISIN,Country,Gross amount,Withholding tax,Net Amount,Currency
    2021-06-01,BAR,Example Corp dividend,US0000000002,US,0.59,€0.09,€0.50,EUR
    2021-03-01,BAZ,Example ETF dividend,IE00000000BB,IE,2.60,$0,€2.60,EUR
""")


def test_parse_tax_doc_sells():
    path = _write_temp(_TAX_DOC_CSV)
    sells, _ = parse_tax_doc(path)
    os.unlink(path)
    assert len(sells) == 1
    s = sells[0]
    assert s["ticker"] == "FOO"
    assert s["date_acquired"] == date(2020, 1, 15)
    assert s["date_sold"] == date(2022, 9, 30)
    assert s["quantity"] == pytest.approx(2.0)
    assert s["cost_basis_usd"] == pytest.approx(100.00)
    assert s["proceeds_usd"] == pytest.approx(120.00)
    assert s["pnl_usd"] == pytest.approx(20.00)
    assert s["isin"] == "US0000000001"
    assert s["country"] == "US"


def test_parse_tax_doc_dividends():
    path = _write_temp(_TAX_DOC_CSV)
    _, divs = parse_tax_doc(path)
    os.unlink(path)
    assert len(divs) == 2


def test_parse_tax_doc_withholding():
    path = _write_temp(_TAX_DOC_CSV)
    _, divs = parse_tax_doc(path)
    os.unlink(path)
    bar = next(d for d in divs if d["ticker"] == "BAR")
    assert bar["gross_eur"] == pytest.approx(0.59)
    assert bar["withholding_eur"] == pytest.approx(0.09)
    assert bar["net_eur"] == pytest.approx(0.50)


def test_parse_tax_doc_zero_withholding():
    path = _write_temp(_TAX_DOC_CSV)
    _, divs = parse_tax_doc(path)
    os.unlink(path)
    baz = next(d for d in divs if d["ticker"] == "BAZ")
    assert baz["withholding_eur"] == pytest.approx(0.0)
    assert baz["gross_eur"] == pytest.approx(2.60)
