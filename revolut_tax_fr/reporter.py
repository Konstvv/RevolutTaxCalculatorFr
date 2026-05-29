from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .calculator import TaxReport
from .forms import FormField

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
_BOX_WIDTH = 44


def _eur(value: float) -> str:
    return f"€{value:,.2f}"


def print_report(report: TaxReport, fields: list[FormField]) -> None:
    border = "═" * _BOX_WIDTH
    print(f"\n╔{border}╗")
    title = f"  Déclaration fiscale France — Année {report.year}  "
    print(f"║{title:^{_BOX_WIDTH}}║")
    print(f"╚{border}╝\n")

    print("DIVIDENDES — Formulaire 2042 (Rubrique 2)")
    _dividers()
    for f in fields:
        if f.code in ("2DC", "2AB"):
            print(f"  Case {f.code:<5} {f.label_fr:<35} {_eur(f.value):>10}")
    print()

    print("PLUS-VALUES / MOINS-VALUES — Formulaires 2042 + 2074")
    _dividers()

    if report.carry_forward_used or report.carry_forward_remaining:
        _print_carry_forward_section(report)

    for f in fields:
        if f.code in ("3VG", "3VH"):
            print(f"  Case {f.code:<5} {f.label_fr:<35} {_eur(f.value):>10}")
    print()

    if report.capital_gains:
        print("  Détail des cessions (Formulaire 2074):")
        for g in report.capital_gains:
            print(
                f"    {g.ticker:<6}  Acq {g.date_acquired}  →  Cession {g.date_sold}"
                f"  {g.quantity:g} titres"
            )
            print(
                f"           Prix revient {_eur(g.cost_basis_eur)}"
                f"  →  Produit {_eur(g.proceeds_eur)}"
                f"  →  Gain/Perte {_eur(g.gain_eur)}"
            )
        print()

    if report.dividends:
        print("  Détail des dividendes :")
        _dividers()
        print(f"  {'Date':<12} {'Ticker':<7} {'Brut':>8} {'Retenue':>9} {'Net':>8}")
        _dividers()
        for d in report.dividends:
            print(
                f"  {d.date!s:<12} {d.ticker:<7}"
                f" {_eur(d.gross_eur):>8} {_eur(d.withholding_eur):>9} {_eur(d.net_eur):>8}"
            )
        _dividers()
        total_gross = sum(d.gross_eur for d in report.dividends)
        total_wht = sum(d.withholding_eur for d in report.dividends)
        total_net = sum(d.net_eur for d in report.dividends)
        print(f"  {'TOTAL':<19} {_eur(total_gross):>8} {_eur(total_wht):>9} {_eur(total_net):>8}")
        print()


def _dividers() -> None:
    print("  " + "-" * 60)


def _print_carry_forward_section(report: TaxReport) -> None:
    """Show the full carry-forward picture: total pool, what was consumed, what remains."""
    from collections import defaultdict

    # Reconstruct total available per year = consumed + remaining
    totals: dict[int, float] = defaultdict(float)
    consumed: dict[int, float] = defaultdict(float)
    for cf in report.carry_forward_used:
        totals[cf.origin_year] += cf.amount_eur
        consumed[cf.origin_year] += cf.amount_eur
    for cf in report.carry_forward_remaining:
        totals[cf.origin_year] += cf.amount_eur

    total_pool = sum(totals.values())
    total_consumed = sum(consumed.values())
    total_remaining = sum(cf.amount_eur for cf in report.carry_forward_remaining)

    print(
        f"\n  Moins-values déclarées en reports disponibles avant {report.year} :"
        f"  {_eur(total_pool)} total"
    )
    for yr in sorted(totals):
        used_amt = consumed.get(yr, 0.0)
        rem_amt = totals[yr] - used_amt
        detail = (
            "imputé en totalité"
            if rem_amt < 0.005
            else f"{_eur(used_amt)} imputé, {_eur(rem_amt)} restant"
        )
        print(f"    • {yr} (3VH déclaré) : {_eur(totals[yr])}  — {detail}")

    if report.carry_forward_used:
        print(
            f"\n  Gain brut {report.year} :                   {_eur(report.gain_before_carry_forward):>10}"
        )
        print(f"  Pertes imputées sur le gain :         {_eur(-total_consumed):>10}")
        _dividers()

    if total_remaining > 0:
        print(f"\n  Report restant pour les années suivantes : {_eur(total_remaining)}")
        for cf in report.carry_forward_remaining:
            print(
                f"    • Pertes {cf.origin_year} : {_eur(cf.amount_eur)}"
                f"  (expire après {cf.origin_year + 10})"
            )

    prior_years = ", ".join(str(y) for y in sorted(totals))
    print(
        f"\n  ATTENTION — Ces reports ({prior_years}) ne sont valables que si vous\n"
        f"  avez bien déclaré case 3VH ces années-là. Pertes d'autres courtiers\n"
        f"  non incluses. Ajustez si nécessaire."
    )


def _eur_fr(value: float) -> str:
    """Format a float as a French-locale number (comma decimal separator)."""
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def render_html(
    report: TaxReport,
    fields: list[FormField],
    show_back_button: bool = False,
) -> str:
    """Render the tax report to an HTML string."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    env.filters["eur"] = _eur_fr
    template = env.get_template("report.html.j2")
    return template.render(
        report=report,
        fields=fields,
        show_back_button=show_back_button,
    )


def write_html(report: TaxReport, fields: list[FormField], output_path: str) -> None:
    html = render_html(report, fields, show_back_button=False)
    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Rapport HTML enregistré : {output_path}")
