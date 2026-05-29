from __future__ import annotations

from datetime import date
from pathlib import Path

from .calculator import compute_tax_report
from .enricher import SecurityCache
from .forms import build_form_2042
from .parser import parse_activity, parse_tax_doc
from .reporter import print_report, write_html


def _default_year() -> int:
    today = date.today()
    # Return the most recent complete calendar year.
    return today.year - 1


def run(
    activity_path: Path,
    tax_doc_path: Path | None,
    year: int,
    output_path: str,
) -> None:
    activity = parse_activity(str(activity_path))

    tax_doc_sells = None
    tax_doc_dividends = None
    if tax_doc_path:
        tax_doc_sells, tax_doc_dividends = parse_tax_doc(str(tax_doc_path))

    cache = SecurityCache()
    report = compute_tax_report(
        year=year,
        activity=activity,
        tax_doc_sells=tax_doc_sells,
        tax_doc_dividends=tax_doc_dividends,
        cache=cache,
    )

    fields = build_form_2042(report)
    print_report(report, fields)
    write_html(report, fields, output_path)
