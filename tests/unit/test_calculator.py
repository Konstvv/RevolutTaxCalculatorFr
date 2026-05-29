"""Tests for the tax computation logic."""

import os
import tempfile
import textwrap
from datetime import date

import pytest

from revolut_tax_fr.calculator import compute_tax_report
from revolut_tax_fr.parser import parse_activity, parse_tax_doc


def _write_temp(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as fh:
        fh.write(content)
    return path


def _cache(**ticker_countries: str):
    """Return an in-memory SecurityCache with explicit ticker→country mappings."""
    from revolut_tax_fr.enricher import SecurityCache, SecurityInfo

    c = SecurityCache(path=None)
    for ticker, country in ticker_countries.items():
        c._data[ticker] = SecurityInfo(ticker=ticker, country=country, source="tax_doc")
    return c


# ---------------------------------------------------------------------------
# Dividend fallback (no tax doc) — fictional tickers/amounts
# ---------------------------------------------------------------------------

# USST = fictional US-domiciled stock (15% withholding)
# ETFIE = fictional Ireland-domiciled ETF (0% withholding)
_ACTIVITY_DIVIDENDS = textwrap.dedent("""\
    Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate
    2020-01-15,USST,DIVIDEND,,,USD 0.20,USD,1.10
    2020-03-01,ETFIE,DIVIDEND,,,EUR 0.75,EUR,1.0000
""")


def test_us_dividend_gross_from_net():
    """US stock net → gross using 15% treaty rate."""
    path = _write_temp(_ACTIVITY_DIVIDENDS)
    activity = parse_activity(path)
    os.unlink(path)

    report = compute_tax_report(2020, activity, None, None, cache=_cache(USST="US", ETFIE="IE"))
    div = next(d for d in report.dividends if d.ticker == "USST")

    net_eur = 0.20 / 1.10
    expected_gross = net_eur / 0.85  # 15% withholding
    expected_wht = expected_gross - net_eur

    # Calculator rounds individual records to 2 decimal places.
    assert div.gross_eur == pytest.approx(expected_gross, abs=0.01)
    assert div.withholding_eur == pytest.approx(expected_wht, abs=0.01)
    assert div.net_eur == pytest.approx(net_eur, abs=0.01)


def test_ie_dividend_zero_withholding():
    """Ireland ETF → 0% withholding, gross = net."""
    path = _write_temp(_ACTIVITY_DIVIDENDS)
    activity = parse_activity(path)
    os.unlink(path)

    report = compute_tax_report(2020, activity, None, None, cache=_cache(USST="US", ETFIE="IE"))
    etf = next(d for d in report.dividends if d.ticker == "ETFIE")

    assert etf.withholding_eur == pytest.approx(0.0)
    assert etf.gross_eur == pytest.approx(etf.net_eur)


def test_box_2dc_sums_gross():
    path = _write_temp(_ACTIVITY_DIVIDENDS)
    activity = parse_activity(path)
    os.unlink(path)

    report = compute_tax_report(2020, activity, None, None, cache=_cache(USST="US", ETFIE="IE"))
    assert report.box_2dc == pytest.approx(sum(d.gross_eur for d in report.dividends), rel=1e-3)


def test_box_2ab_sums_withholding():
    path = _write_temp(_ACTIVITY_DIVIDENDS)
    activity = parse_activity(path)
    os.unlink(path)

    report = compute_tax_report(2020, activity, None, None, cache=_cache(USST="US", ETFIE="IE"))
    assert report.box_2ab == pytest.approx(
        sum(d.withholding_eur for d in report.dividends), rel=1e-3
    )


# ---------------------------------------------------------------------------
# Capital gains: FIFO + box aggregation — fictional ticker/price/date
# ---------------------------------------------------------------------------

# FOO: bought 2020-01-15 at $100 total, sold 2022-09-30 at $120 total, FX 1.20
# gain = (120 - 100) / 1.20 = €16.67
_ACTIVITY_FOO = textwrap.dedent("""\
    Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate
    2020-01-15T10:00:00.000Z,FOO,BUY - MARKET,2,USD 50.00,USD 100.00,USD,1.20
    2022-09-30T10:00:00.000Z,FOO,SELL - MARKET,2,USD 60.00,USD 120.00,USD,1.20
""")


def test_capital_gain_computation():
    path = _write_temp(_ACTIVITY_FOO)
    activity = parse_activity(path)
    os.unlink(path)

    report = compute_tax_report(2022, activity, None, None)
    assert len(report.capital_gains) == 1

    g = report.capital_gains[0]
    assert g.ticker == "FOO"
    assert g.date_acquired == date(2020, 1, 15)
    assert g.date_sold == date(2022, 9, 30)
    assert g.quantity == pytest.approx(2.0)
    assert g.cost_basis_eur == pytest.approx(100.00 / 1.20, rel=1e-4)
    assert g.proceeds_eur == pytest.approx(120.00 / 1.20, rel=1e-4)
    assert g.gain_eur == pytest.approx(g.proceeds_eur - g.cost_basis_eur, rel=1e-6)


def test_capital_gain_goes_to_box_3vg():
    path = _write_temp(_ACTIVITY_FOO)
    activity = parse_activity(path)
    os.unlink(path)

    report = compute_tax_report(2022, activity, None, None)
    assert report.box_3vg == pytest.approx(20.00 / 1.20, abs=0.02)  # (120-100)/1.20 = 16.67
    assert report.box_3vh == pytest.approx(0.0)


def test_capital_loss_goes_to_box_3vh():
    """When gain is negative, box_3vh receives the loss and box_3vg is zero."""
    activity_loss = textwrap.dedent("""\
        Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate
        2020-01-01T00:00:00Z,DLST,BUY - MARKET,10,USD 5.00,USD 50.00,USD,1.10
        2020-12-15T00:00:00Z,DLST,SELL - STOP,10,USD 4.80,USD 47.00,USD,1.10
    """)
    path = _write_temp(activity_loss)
    activity = parse_activity(path)
    os.unlink(path)

    report = compute_tax_report(2020, activity, None, None)
    assert report.box_3vg == pytest.approx(0.0)
    assert report.box_3vh > 0  # small loss — exact value tested in integration


def test_year_filter_excludes_other_years():
    """Selling FOO in 2022 should not appear in the 2021 capital gains report."""
    path = _write_temp(_ACTIVITY_FOO)
    activity = parse_activity(path)
    os.unlink(path)

    report = compute_tax_report(2021, activity, None, None)
    assert len(report.capital_gains) == 0
    assert report.box_3vg == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Tax doc dividends override activity fallback
# ---------------------------------------------------------------------------

_TAX_DOC_SIMPLE = textwrap.dedent("""\
    Income from Sells
    Date acquired,Date sold,Symbol,Security name,ISIN,Country,Quantity,Cost basis,Gross proceeds,Gross PnL,Currency

    Other income & fees
    Date,Symbol,Security name,ISIN,Country,Gross amount,Withholding tax,Net Amount,Currency
    2020-06-01,DIV,Example dividend,US0000000001,US,0.50,€0.08,€0.42,EUR
""")


def test_tax_doc_dividends_used_directly():
    """When a tax doc is provided, its values overwrite the fallback computation."""
    activity_csv = textwrap.dedent("""\
        Date,Ticker,Type,Quantity,Price per share,Total Amount,Currency,FX Rate
        2020-06-01T00:00:00Z,DIV,DIVIDEND,,,USD 0.38,USD,1.10
    """)
    a_path = _write_temp(activity_csv)
    d_path = _write_temp(_TAX_DOC_SIMPLE)

    activity = parse_activity(a_path)
    _, divs = parse_tax_doc(d_path)
    os.unlink(a_path)
    os.unlink(d_path)

    report = compute_tax_report(2020, activity, None, divs)
    div = next(d for d in report.dividends if d.ticker == "DIV")

    # Tax doc values (not the back-calculated ones from activity)
    assert div.gross_eur == pytest.approx(0.50)
    assert div.withholding_eur == pytest.approx(0.08)
    assert div.net_eur == pytest.approx(0.42)
