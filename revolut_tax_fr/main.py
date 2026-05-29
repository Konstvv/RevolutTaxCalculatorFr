from __future__ import annotations

import argparse
import sys
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="revolut-tax",
        description="Génère un rapport fiscal français depuis les relevés Revolut.",
    )
    parser.add_argument(
        "--activity",
        "-a",
        required=True,
        metavar="FILE",
        help="Relevé d'activité Revolut (CSV complet avec toutes les transactions).",
    )
    parser.add_argument(
        "--tax-doc",
        "-t",
        metavar="FILE",
        default=None,
        help="Document fiscal annuel Revolut (CSV avec dividendes et cessions).",
    )
    parser.add_argument(
        "--year",
        "-y",
        type=int,
        default=None,
        metavar="YEAR",
        help=f"Année fiscale à déclarer (défaut : {_default_year()}).",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="FILE",
        default=None,
        help="Chemin du rapport HTML généré (défaut : tax_report_YEAR.html).",
    )

    args = parser.parse_args(argv)

    # Validate inputs.
    activity_path = Path(args.activity)
    if not activity_path.exists():
        sys.exit(f"Erreur : fichier introuvable — {activity_path}")

    tax_doc_path = Path(args.tax_doc) if args.tax_doc else None
    if tax_doc_path and not tax_doc_path.exists():
        sys.exit(f"Erreur : fichier introuvable — {tax_doc_path}")

    year = args.year or _default_year()
    output_path = args.output or f"tax_report_{year}.html"

    # Parse.
    print(f"Lecture du relevé d'activité : {activity_path}")
    activity = parse_activity(str(activity_path))

    tax_doc_sells = None
    tax_doc_dividends = None
    if tax_doc_path:
        print(f"Lecture du document fiscal : {tax_doc_path}")
        tax_doc_sells, tax_doc_dividends = parse_tax_doc(str(tax_doc_path))

    # Build security cache (loads ~/.revolut_tax_fr/securities.json if it exists).
    cache = SecurityCache()

    # Compute.
    print(f"Calcul de la déclaration pour l'année {year}…")
    report = compute_tax_report(
        year=year,
        activity=activity,
        tax_doc_sells=tax_doc_sells,
        tax_doc_dividends=tax_doc_dividends,
        cache=cache,
    )

    fields = build_form_2042(report)

    # Output.
    print_report(report, fields)
    write_html(report, fields, output_path)


if __name__ == "__main__":
    main()
