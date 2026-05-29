from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from .config import withholding_rate
from .enricher import SecurityCache
from .parser import ActivityRow, TaxDocDividends, TaxDocSells
from .portfolio import Portfolio


@dataclass
class CapitalGainRecord:
    ticker: str
    isin: str | None
    country: str | None
    security_name: str | None
    date_acquired: date
    date_sold: date
    quantity: float
    cost_basis_eur: float
    proceeds_eur: float
    gain_eur: float


@dataclass
class DividendRecord:
    date: date
    ticker: str
    isin: str | None
    country: str | None
    security_name: str | None
    gross_eur: float
    withholding_eur: float
    net_eur: float


@dataclass
class CarryForwardLoss:
    """A capital loss from a prior year that can offset future gains (up to 10 years)."""

    origin_year: int
    amount_eur: float  # always positive


@dataclass
class TaxReport:
    year: int
    dividends: list[DividendRecord] = field(default_factory=list)
    capital_gains: list[CapitalGainRecord] = field(default_factory=list)

    # Carry-forward bookkeeping
    gain_before_carry_forward: float = 0.0
    carry_forward_used: list[CarryForwardLoss] = field(default_factory=list)
    carry_forward_remaining: list[CarryForwardLoss] = field(default_factory=list)

    # Form boxes
    box_2dc: float = 0.0  # gross dividends
    box_2ab: float = 0.0  # foreign withholding credit
    box_3vg: float = 0.0  # net taxable gains AFTER applying carry-forward (≥ 0)
    box_3vh: float = 0.0  # current-year NEW losses to carry forward (≥ 0)


_BUY_TYPES = {"BUY - MARKET", "BUY - LIMIT", "BUY - STOP"}
_SELL_TYPES = {"SELL - MARKET", "SELL - LIMIT", "SELL - STOP"}


def _usd_to_eur(amount: float, fx_rate: float) -> float:
    """Convert amount from transaction currency to EUR.

    The FX rate in Revolut CSV means: 1 EUR = fx_rate units of transaction currency.
    For EUR-denominated transactions fx_rate is 1.0.
    """
    if fx_rate == 0:
        return 0.0
    return amount / fx_rate


# ---------------------------------------------------------------------------
# Carry-forward helpers
# ---------------------------------------------------------------------------


def _evolve_pool(
    year: int,
    net_gain: float,
    pool: list[CarryForwardLoss],
) -> list[CarryForwardLoss]:
    """Return the updated carry-forward pool after a completed tax year.

    If the year has a net gain, oldest losses are consumed first.
    If the year has a net loss, it is appended to the pool.
    The current year's gain/loss result is computed on the TOTAL net —
    French tax law requires netting all transactions within a year before
    applying any carry-forward (CGI Art. 150-0 D, 11).

    Losses expire after 10 years: a loss from year Y can only be applied
    in years Y+1 through Y+10 inclusive.
    """
    # Expire losses that can no longer be applied in `year` or later.
    pool = [loss for loss in pool if year - loss.origin_year <= 10]

    if net_gain < 0:
        return [*pool, CarryForwardLoss(year, -net_gain)]

    # Net gain: consume oldest losses first.
    remaining = net_gain
    new_pool: list[CarryForwardLoss] = []
    for loss in pool:
        if remaining <= 0:
            new_pool.append(loss)
        elif loss.amount_eur <= remaining:
            remaining -= loss.amount_eur  # fully consumed
        else:
            new_pool.append(CarryForwardLoss(loss.origin_year, loss.amount_eur - remaining))
            remaining = 0.0
    return new_pool


def _apply_pool_to_gain(
    net_gain: float,
    pool: list[CarryForwardLoss],
) -> tuple[float, list[CarryForwardLoss], list[CarryForwardLoss]]:
    """Apply carry-forward losses against a positive net gain.

    Returns:
        adjusted_gain  — taxable gain after carry-forward (≥ 0)
        used           — losses consumed (for reporting)
        remaining      — unused losses still available for future years
    """
    used: list[CarryForwardLoss] = []
    remaining_pool: list[CarryForwardLoss] = []
    remaining_gain = net_gain

    for loss in pool:
        if remaining_gain <= 0:
            remaining_pool.append(loss)
        elif loss.amount_eur <= remaining_gain:
            used.append(loss)
            remaining_gain -= loss.amount_eur
        else:
            used.append(CarryForwardLoss(loss.origin_year, remaining_gain))
            remaining_pool.append(
                CarryForwardLoss(loss.origin_year, loss.amount_eur - remaining_gain)
            )
            remaining_gain = 0.0

    return max(0.0, remaining_gain), used, remaining_pool


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------


def compute_tax_report(
    year: int,
    activity: list[ActivityRow],
    tax_doc_sells: TaxDocSells | None,
    tax_doc_dividends: TaxDocDividends | None,
    cache: SecurityCache | None = None,
) -> TaxReport:
    if cache is None:
        cache = SecurityCache()

    # Populate the cache from the tax document first — it is the most reliable
    # source and enriches all securities before any fallback lookups are needed.
    if tax_doc_sells or tax_doc_dividends:
        cache.populate_from_tax_doc(
            tax_doc_sells or [],
            tax_doc_dividends or [],
        )

    report = TaxReport(year=year)

    # --- Capital gains: single FIFO pass over the full activity history ---
    # We replay ALL years so that FIFO lot state is always correct, then
    # bucket the resulting gains by year for carry-forward computation.
    portfolio = Portfolio()
    gains_by_year: dict[int, list[CapitalGainRecord]] = defaultdict(list)

    for row in activity:
        txtype = row.type
        ticker = row.ticker
        if not ticker:
            continue

        if txtype in _BUY_TYPES:
            if row.quantity is None or row.quantity == 0:
                continue
            portfolio.buy(
                ticker=ticker,
                purchase_date=row.date.date(),
                quantity=row.quantity,
                total_amount=row.total_amount,
                fx_rate=row.fx_rate,
            )

        elif txtype in _SELL_TYPES:
            if row.quantity is None or row.quantity == 0:
                continue

            sell_date = row.date.date()

            try:
                cost_eur, proceeds_eur = portfolio.sell(
                    ticker=ticker,
                    quantity_sold=row.quantity,
                    total_amount=row.total_amount,
                    fx_rate=row.fx_rate,
                )
            except ValueError as exc:
                print(f"WARNING: {exc}")
                continue

            info = cache.enrich(ticker)
            gains_by_year[sell_date.year].append(
                CapitalGainRecord(
                    ticker=ticker,
                    isin=info.isin,
                    country=info.country,
                    security_name=info.name,
                    date_acquired=_find_acquisition_date(activity, ticker, sell_date),
                    date_sold=sell_date,
                    quantity=row.quantity,
                    cost_basis_eur=cost_eur,
                    proceeds_eur=proceeds_eur,
                    gain_eur=proceeds_eur - cost_eur,
                )
            )

    # --- Build carry-forward pool from all years before the target year ---
    carry_pool: list[CarryForwardLoss] = []
    for prior_year in sorted(gains_by_year):
        if prior_year >= year:
            continue
        net = sum(g.gain_eur for g in gains_by_year[prior_year])
        carry_pool = _evolve_pool(prior_year, net, carry_pool)
    # Final expiry pass for the target year itself (handles gaps in transaction history).
    carry_pool = [loss for loss in carry_pool if year - loss.origin_year <= 10]

    # --- Apply carry-forward to the current year ---
    report.capital_gains = gains_by_year.get(year, [])
    raw_net = sum(g.gain_eur for g in report.capital_gains)
    report.gain_before_carry_forward = round(raw_net, 2)

    if raw_net > 0 and carry_pool:
        adjusted, used, remaining = _apply_pool_to_gain(raw_net, carry_pool)
        report.box_3vg = round(adjusted, 2)
        report.box_3vh = 0.0
        report.carry_forward_used = used
        report.carry_forward_remaining = remaining
    elif raw_net < 0:
        report.box_3vg = 0.0
        report.box_3vh = round(-raw_net, 2)
        report.carry_forward_used = []
        report.carry_forward_remaining = carry_pool  # existing pool unchanged
    else:
        report.box_3vg = round(max(0.0, raw_net), 2)
        report.box_3vh = 0.0
        report.carry_forward_used = []
        report.carry_forward_remaining = carry_pool

    # --- Dividends ---
    if tax_doc_dividends:
        year_divs = [d for d in tax_doc_dividends if d.get("date") and d["date"].year == year]
        if year_divs:
            report.dividends = [
                DividendRecord(
                    date=d["date"],
                    ticker=d["ticker"],
                    isin=d.get("isin"),
                    country=d.get("country"),
                    security_name=d.get("security_name"),
                    gross_eur=d["gross_eur"],
                    withholding_eur=d["withholding_eur"],
                    net_eur=d["net_eur"],
                )
                for d in year_divs
            ]
        else:
            report.dividends = _compute_dividends_from_activity(year, activity, cache)
    else:
        report.dividends = _compute_dividends_from_activity(year, activity, cache)

    # --- Aggregate dividend boxes ---
    report.box_2dc = round(sum(d.gross_eur for d in report.dividends), 2)
    report.box_2ab = round(sum(d.withholding_eur for d in report.dividends), 2)

    return report


def _find_acquisition_date(activity: list[ActivityRow], ticker: str, before: date) -> date:
    """Return the date of the first BUY for `ticker` that precedes `before`."""
    for row in activity:
        if row.ticker == ticker and row.type in _BUY_TYPES:
            d = row.date.date()
            if d < before:
                return d
    return before


def _compute_dividends_from_activity(
    year: int,
    activity: list[ActivityRow],
    cache: SecurityCache,
) -> list[DividendRecord]:
    """Fallback: derive dividends from the activity statement.

    Gross amounts and withholding are back-calculated from the net amounts
    using the withholding rates in config (ISIN overrides take priority over
    country-level defaults).
    """
    records: list[DividendRecord] = []
    corrections: dict[str, float] = {}

    for row in activity:
        if row.date.year != year or not row.ticker:
            continue

        if row.type == "DIVIDEND TAX (CORRECTION)":
            corrections[row.ticker] = corrections.get(row.ticker, 0.0) + _usd_to_eur(
                row.total_amount, row.fx_rate
            )
            continue

        if row.type != "DIVIDEND":
            continue

        info = cache.enrich(row.ticker)
        rate = withholding_rate(info.isin, info.country)
        net_eur = _usd_to_eur(row.total_amount, row.fx_rate)
        # Back-calculate gross: net = gross * (1 - rate)
        gross_eur = net_eur / (1.0 - rate) if rate < 1.0 else net_eur
        withholding_eur = gross_eur - net_eur

        records.append(
            DividendRecord(
                date=row.date.date(),
                ticker=row.ticker,
                isin=info.isin,
                country=info.country,
                security_name=info.name,
                gross_eur=round(gross_eur, 2),
                withholding_eur=round(withholding_eur, 2),
                net_eur=round(net_eur, 2),
            )
        )

    for ticker, correction_eur in corrections.items():
        if abs(correction_eur) < 1e-6:
            continue
        for rec in reversed(records):
            if rec.ticker == ticker:
                rec.withholding_eur = round(rec.withholding_eur + correction_eur, 2)
                rec.gross_eur = round(rec.net_eur + rec.withholding_eur, 2)
                break

    return records
