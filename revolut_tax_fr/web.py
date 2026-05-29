from __future__ import annotations

import argparse
import logging
import tempfile
from datetime import date
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .calculator import compute_tax_report
from .enricher import SecurityCache
from .forms import build_form_2042
from .parser import parse_activity, parse_tax_doc
from .reporter import render_html

_log = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

app = FastAPI(title="RevolutTaxFr")
_templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


def _default_year() -> int:
    return date.today().year - 1


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return _templates.TemplateResponse(
        request,
        "upload.html.j2",
        {"year": _default_year(), "error": None},
    )


@app.post("/compute", response_class=HTMLResponse)
async def compute(
    request: Request,
    activity: UploadFile = File(...),  # noqa: B008
    tax_doc: UploadFile | None = File(default=None),  # noqa: B008
    year: int = Form(default=None),
) -> HTMLResponse:
    if year is None:
        year = _default_year()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            activity_path = tmp_path / "activity.csv"
            activity_path.write_bytes(await activity.read())

            tax_doc_path: Path | None = None
            if tax_doc and tax_doc.filename:
                tax_doc_path = tmp_path / "tax_doc.csv"
                tax_doc_path.write_bytes(await tax_doc.read())

            activity_rows = parse_activity(str(activity_path))

            tax_doc_sells = None
            tax_doc_dividends = None
            if tax_doc_path:
                tax_doc_sells, tax_doc_dividends = parse_tax_doc(str(tax_doc_path))

            cache = SecurityCache()
            report = compute_tax_report(
                year=year,
                activity=activity_rows,
                tax_doc_sells=tax_doc_sells,
                tax_doc_dividends=tax_doc_dividends,
                cache=cache,
            )
            fields = build_form_2042(report)
            html = render_html(report, fields, show_back_button=True)
            return HTMLResponse(content=html)

        except Exception as exc:
            _log.exception("Error processing uploaded files")
            return _templates.TemplateResponse(
                request,
                "upload.html.j2",
                {"year": year, "error": f"Erreur lors du traitement : {exc}"},
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="revolut-tax-web",
        description="Serveur web pour générer le rapport fiscal Revolut.",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
