from __future__ import annotations

from typer.testing import CliRunner

runner = CliRunner()


def test_compute_missing_activity_arg():
    """--activity is required; omitting it should fail."""
    from revolut_tax_fr.cli import compute_app

    result = runner.invoke(compute_app, [])
    assert result.exit_code != 0


def test_compute_file_not_found():
    """Passing a non-existent file should exit 1 with a French error message."""
    from revolut_tax_fr.cli import compute_app

    result = runner.invoke(compute_app, ["--activity", "/nonexistent/path.csv"])
    assert result.exit_code == 1
    assert "introuvable" in result.output


def test_compute_tax_doc_not_found():
    """Passing a non-existent tax doc should exit 1 with a French error message."""
    import tempfile

    from revolut_tax_fr.cli import compute_app

    with tempfile.NamedTemporaryFile(suffix=".csv") as f:
        result = runner.invoke(
            compute_app,
            ["--activity", f.name, "--tax-doc", "/nonexistent/tax.csv"],
        )
    assert result.exit_code == 1
    assert "introuvable" in result.output


def test_compute_help():
    """--help should list all four options."""
    from revolut_tax_fr.cli import compute_app

    result = runner.invoke(compute_app, ["--help"])
    assert result.exit_code == 0
    assert "--activity" in result.output
    assert "--tax-doc" in result.output
    assert "--year" in result.output
    assert "--output" in result.output


def test_serve_help():
    """--help should list --host and --port."""
    from revolut_tax_fr.cli import serve_app

    result = runner.invoke(serve_app, ["--help"])
    assert result.exit_code == 0
    assert "--host" in result.output
    assert "--port" in result.output
