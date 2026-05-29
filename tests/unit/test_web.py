"""Tests for the web UI: render_html() and FastAPI routes."""

from __future__ import annotations

import io
import pathlib

import pytest
from fastapi.testclient import TestClient

from revolut_tax_fr.web import app

client = TestClient(app)

TEST_DATA = pathlib.Path(__file__).parent.parent.parent / "test_data"
ACTIVITY = TEST_DATA / "activity_statement.csv"
TAX_DOC = TEST_DATA / "tax_document_2025.csv"


def _make_report():
    """Build a minimal TaxReport for unit tests (no file I/O needed)."""
    from revolut_tax_fr.calculator import TaxReport
    from revolut_tax_fr.forms import build_form_2042

    report = TaxReport(year=2025, box_2dc=50.00, box_2ab=3.00, box_3vg=0.0, box_3vh=0.0)
    fields = build_form_2042(report)
    return report, fields


def test_render_html_returns_string():
    from revolut_tax_fr.reporter import render_html

    report, fields = _make_report()
    html = render_html(report, fields)
    assert isinstance(html, str)
    assert "2DC" in html
    assert "50,00" in html  # French number format (comma decimal separator)


def test_render_html_no_back_button_by_default():
    from revolut_tax_fr.reporter import render_html

    report, fields = _make_report()
    html = render_html(report, fields)
    assert "Nouveau rapport" not in html


def test_render_html_with_back_button():
    from revolut_tax_fr.reporter import render_html

    report, fields = _make_report()
    html = render_html(report, fields, show_back_button=True)
    assert "Nouveau rapport" in html
    assert 'href="/"' in html


def test_get_index():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Relevé d'activité" in resp.text
    assert "Document fiscal" in resp.text
    assert "Générer le rapport" in resp.text


@pytest.mark.skipif(not ACTIVITY.exists(), reason="test_data/ not present")
def test_compute_valid():
    with open(ACTIVITY, "rb") as fa, open(TAX_DOC, "rb") as ft:
        resp = client.post(
            "/compute",
            data={"year": "2025"},
            files={
                "activity": ("activity.csv", fa, "text/csv"),
                "tax_doc": ("tax_doc.csv", ft, "text/csv"),
            },
        )
    assert resp.status_code == 200
    assert "2DC" in resp.text
    assert "Nouveau rapport" in resp.text
    assert "Erreur" not in resp.text


@pytest.mark.skipif(not ACTIVITY.exists(), reason="test_data/ not present")
def test_compute_year_override():
    with open(ACTIVITY, "rb") as fa:
        resp = client.post(
            "/compute",
            data={"year": "2024"},
            files={"activity": ("activity.csv", fa, "text/csv")},
        )
    assert resp.status_code == 200
    assert "2024" in resp.text
    assert "Nouveau rapport" in resp.text


def test_compute_bad_csv():
    # An unclosed quote forces polars to raise a ComputeError during CSV parsing
    bad_content = b'col1,col2\n"unclosed quote,val2\nval3,val4'
    resp = client.post(
        "/compute",
        data={"year": "2025"},
        files={"activity": ("bad.csv", io.BytesIO(bad_content), "text/csv")},
    )
    assert resp.status_code == 200
    assert "Erreur" in resp.text
    # Should re-show the upload form, not the report
    assert "Relevé d'activité" in resp.text


def test_compute_missing_activity():
    resp = client.post("/compute", data={"year": "2025"})
    assert resp.status_code == 422
