from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

import polars as pl


@dataclass
class ActivityRow:
    date: datetime
    ticker: str | None
    type: str
    quantity: float | None
    price_per_share: float | None
    total_amount: float
    currency: str
    fx_rate: float  # 1 EUR = fx_rate units of `currency`


_CURRENCY_PREFIX = re.compile(r"^[A-Z]{3}\s+")
_CURRENCY_SYMBOLS = re.compile(r"[€$\s]")


def _strip_currency(value: str | None) -> float | None:
    if value is None or (isinstance(value, float)):
        return value
    s = str(value).strip()
    if not s:
        return None
    s = _CURRENCY_PREFIX.sub("", s)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_activity(path: str) -> list[ActivityRow]:
    """Parse a Revolut account activity statement CSV into ActivityRow objects."""
    df = pl.read_csv(path, infer_schema_length=0)

    rows: list[ActivityRow] = []
    for r in df.iter_rows(named=True):
        ticker = r.get("Ticker") or None
        if ticker == "":
            ticker = None

        quantity_raw = r.get("Quantity") or None
        price_raw = r.get("Price per share") or None
        total_raw = r.get("Total Amount") or ""
        currency = (r.get("Currency") or "EUR").strip()
        fx_raw = r.get("FX Rate") or "1.0"

        quantity = _strip_currency(quantity_raw)
        price = _strip_currency(price_raw)
        total = _strip_currency(total_raw)
        fx = float(fx_raw) if fx_raw else 1.0

        if total is None:
            continue

        date_str = r.get("Date", "")
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        rows.append(
            ActivityRow(
                date=dt,
                ticker=ticker,
                type=(r.get("Type") or "").strip(),
                quantity=quantity,
                price_per_share=price,
                total_amount=total,
                currency=currency,
                fx_rate=fx,
            )
        )

    rows.sort(key=lambda r: r.date)
    return rows


# ---------------------------------------------------------------------------
# Tax document parser
# ---------------------------------------------------------------------------

TaxDocSells = list[dict]
TaxDocDividends = list[dict]


def _parse_amount(value: str | None) -> float:
    if value is None:
        return 0.0
    s = _CURRENCY_SYMBOLS.sub("", str(value)).strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_tax_doc(path: str) -> tuple[TaxDocSells, TaxDocDividends]:
    """Parse a Revolut annual tax document CSV.

    Returns a pair of (sells, dividends) as lists of plain dicts.
    """
    with open(path, encoding="utf-8") as fh:
        raw_lines = fh.readlines()

    # Split the file into the two sections delimited by blank lines.
    sections: list[list[str]] = []
    current: list[str] = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            if current:
                sections.append(current)
                current = []
        else:
            current.append(stripped)
    if current:
        sections.append(current)

    # First non-blank section whose first line is a title → skip; second line is the header.
    sells: TaxDocSells = []
    dividends: TaxDocDividends = []

    for section in sections:
        if len(section) < 2:
            continue

        header_line = section[0]

        # Section 1: capital gains ("Income from Sells")
        if "Income from Sells" in header_line or "Date acquired" in header_line:
            # Find the actual CSV header row
            col_line_idx = 0 if "Date acquired" in section[0] else 1
            if col_line_idx >= len(section):
                continue
            columns = [c.strip() for c in section[col_line_idx].split(",")]
            for data_line in section[col_line_idx + 1 :]:
                parts = [p.strip() for p in data_line.split(",")]
                if len(parts) < len(columns):
                    continue
                row = dict(zip(columns, parts, strict=False))
                sells.append(
                    {
                        "date_acquired": _parse_date(row.get("Date acquired")),
                        "date_sold": _parse_date(row.get("Date sold")),
                        "ticker": row.get("Symbol", "").strip(),
                        "security_name": row.get("Security name", "").strip(),
                        "isin": row.get("ISIN", "").strip() or None,
                        "country": row.get("Country", "").strip() or None,
                        "quantity": _parse_amount(row.get("Quantity")),
                        "cost_basis_usd": _parse_amount(row.get("Cost basis")),
                        "proceeds_usd": _parse_amount(row.get("Gross proceeds")),
                        "pnl_usd": _parse_amount(row.get("Gross PnL")),
                        "currency": row.get("Currency", "USD").strip(),
                    }
                )

        # Section 2: dividends ("Other income & fees")
        elif "Other income" in header_line or "Gross amount" in header_line:
            col_line_idx = 0 if "Date" in section[0] and "," in section[0] else 1
            if col_line_idx >= len(section):
                continue
            columns = [c.strip() for c in section[col_line_idx].split(",")]
            for data_line in section[col_line_idx + 1 :]:
                parts = [p.strip() for p in data_line.split(",")]
                if len(parts) < len(columns):
                    continue
                row = dict(zip(columns, parts, strict=False))
                dividends.append(
                    {
                        "date": _parse_date(row.get("Date")),
                        "ticker": row.get("Symbol", "").strip(),
                        "security_name": row.get("Security name", "").strip(),
                        "isin": row.get("ISIN", "").strip() or None,
                        "country": row.get("Country", "").strip() or None,
                        "gross_eur": _parse_amount(row.get("Gross amount")),
                        "withholding_eur": _parse_amount(row.get("Withholding tax")),
                        "net_eur": _parse_amount(row.get("Net Amount")),
                    }
                )

    return sells, dividends


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None
