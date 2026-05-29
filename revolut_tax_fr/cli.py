from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from .main import _default_year, run
from .web import serve as _serve

compute_app = typer.Typer(add_completion=False)
serve_app = typer.Typer(add_completion=False)


def _console() -> Console:
    # Lazy factory so typer.testing.CliRunner's sys.stdout patch is captured.
    return Console(file=sys.stdout, highlight=False, markup=True)


# Module-level option defaults to avoid B008 linter errors
_ACTIVITY_OPTION = typer.Option(
    ...,
    "--activity",
    "-a",
    help="Relevé d'activité Revolut (CSV complet avec toutes les transactions).",
    metavar="FILE",
)
_TAX_DOC_OPTION = typer.Option(
    None,
    "--tax-doc",
    "-t",
    help="Document fiscal annuel Revolut (CSV avec dividendes et cessions).",
    metavar="FILE",
)
_YEAR_OPTION = typer.Option(
    None,
    "--year",
    "-y",
    help="Année fiscale à déclarer (défaut : année précédente).",
    metavar="YEAR",
)
_OUTPUT_OPTION = typer.Option(
    None,
    "--output",
    "-o",
    help="Chemin du rapport HTML généré (défaut : tax_report_YEAR.html).",
    metavar="FILE",
)


@compute_app.command()
def compute(
    activity: Path = _ACTIVITY_OPTION,
    tax_doc: Path | None = _TAX_DOC_OPTION,
    year: int | None = _YEAR_OPTION,
    output: Path | None = _OUTPUT_OPTION,
) -> None:
    """Génère un rapport fiscal français depuis les relevés Revolut."""
    console = _console()

    if not activity.exists():
        console.print(f"[red bold]Erreur :[/red bold] fichier introuvable — {activity}")
        raise typer.Exit(1)

    if tax_doc is not None and not tax_doc.exists():
        console.print(f"[red bold]Erreur :[/red bold] fichier introuvable — {tax_doc}")
        raise typer.Exit(1)

    resolved_year = year or _default_year()
    output_path = str(output) if output else f"tax_report_{resolved_year}.html"

    console.print(f"[bold]Lecture du relevé d'activité :[/bold] {activity}")
    if tax_doc:
        console.print(f"[bold]Lecture du document fiscal :[/bold] {tax_doc}")
    console.print(f"[bold]Calcul de la déclaration pour l'année {resolved_year}…[/bold]")

    run(
        activity_path=activity,
        tax_doc_path=tax_doc,
        year=resolved_year,
        output_path=output_path,
    )

    console.print(f"\n[green]Rapport généré :[/green] {output_path}")


@serve_app.command()
def serve(
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        help="Adresse d'écoute du serveur.",
    ),
    port: int = typer.Option(
        8080,
        "--port",
        help="Port d'écoute du serveur.",
    ),
) -> None:
    """Lance le serveur web pour générer le rapport fiscal Revolut."""
    console = _console()
    display_host = "localhost" if host == "0.0.0.0" else host
    console.print(f"[bold]Serveur démarré sur[/bold] http://{display_host}:{port}")
    _serve(host=host, port=port)
