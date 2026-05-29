"""End-to-end tests using local Revolut test data files.

Place your Revolut exports in test_data/ as:
  activity_statement.csv   — full activity export
  tax_document_2025.csv    — annual tax document for the target year

These files are gitignored and never committed.
"""

import pathlib

import pytest

from revolut_tax_fr.calculator import compute_tax_report
from revolut_tax_fr.parser import parse_activity, parse_tax_doc

TEST_DATA = pathlib.Path(__file__).parent.parent.parent / "test_data"
ACTIVITY = TEST_DATA / "activity_statement.csv"
TAX_DOC = TEST_DATA / "tax_document_2025.csv"

pytestmark = pytest.mark.skipif(
    not ACTIVITY.exists(),
    reason="Test data files not present (see test_data/ instructions in module docstring)",
)


@pytest.fixture(scope="module")
def activity():
    return parse_activity(str(ACTIVITY))


@pytest.fixture(scope="module")
def tax_doc():
    sells, divs = parse_tax_doc(str(TAX_DOC))
    return sells, divs


# ---------------------------------------------------------------------------
# Year with tax document — structural tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def report_with_tax_doc(activity, tax_doc):
    sells, divs = tax_doc
    return compute_tax_report(2025, activity, sells, divs)


def test_report_with_tax_doc_has_dividends(report_with_tax_doc):
    """Tax document path produces dividend records."""
    assert len(report_with_tax_doc.dividends) > 0
    assert report_with_tax_doc.box_2dc > 0


def test_report_with_tax_doc_has_withholding(report_with_tax_doc):
    """Some dividends should have withholding tax."""
    assert report_with_tax_doc.box_2ab >= 0


def test_report_with_tax_doc_capital_gains_structure(report_with_tax_doc):
    """Capital gains/losses are non-negative in their respective boxes."""
    assert report_with_tax_doc.box_3vg >= 0
    assert report_with_tax_doc.box_3vh >= 0


def test_report_carry_forward_consistency(report_with_tax_doc):
    """gain_before_carry_forward + box values are internally consistent."""
    raw = report_with_tax_doc.gain_before_carry_forward
    if raw > 0:
        # Either a taxable gain remains or it was absorbed by carry-forward
        total_cf_used = sum(cf.amount_eur for cf in report_with_tax_doc.carry_forward_used)
        assert report_with_tax_doc.box_3vg == pytest.approx(max(0.0, raw - total_cf_used), abs=0.05)


def test_report_dividends_all_positive(report_with_tax_doc):
    """Every dividend record has a positive gross amount."""
    for div in report_with_tax_doc.dividends:
        assert div.gross_eur >= 0
        assert div.withholding_eur >= 0
        assert div.net_eur >= 0


# ---------------------------------------------------------------------------
# Year without tax document — structural tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def report_without_tax_doc(activity):
    return compute_tax_report(2024, activity, None, None)


def test_report_without_tax_doc_runs(report_without_tax_doc):
    """Activity-only path completes without error."""
    assert report_without_tax_doc.year == 2024


def test_report_without_tax_doc_boxes_non_negative(report_without_tax_doc):
    assert report_without_tax_doc.box_2dc >= 0
    assert report_without_tax_doc.box_2ab >= 0
    assert report_without_tax_doc.box_3vg >= 0
    assert report_without_tax_doc.box_3vh >= 0


def test_report_without_tax_doc_gain_loss_exclusive(report_without_tax_doc):
    """3VG and 3VH cannot both be non-zero at the same time."""
    assert not (report_without_tax_doc.box_3vg > 0 and report_without_tax_doc.box_3vh > 0)


def test_report_dividends_year_filtered(report_without_tax_doc):
    for d in report_without_tax_doc.dividends:
        assert d.date.year == 2024
