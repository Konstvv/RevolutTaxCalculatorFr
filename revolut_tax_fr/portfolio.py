from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date


@dataclass
class Lot:
    date: date
    quantity: float
    price_per_share_eur: float  # total purchase cost / quantity, in EUR


class Portfolio:
    """FIFO (PEPS) cost-basis tracker.

    Both cost basis and proceeds use the CSV's `total_amount` column —
    the actual money paid (buy) or received (sell) including Revolut's
    spread. This is more accurate than price * quantity because the spread
    is a real transaction cost that affects the taxable gain.
    """

    def __init__(self) -> None:
        self.lots: dict[str, deque[Lot]] = defaultdict(deque)

    def buy(
        self,
        ticker: str,
        purchase_date: date,
        quantity: float,
        total_amount: float,
        fx_rate: float,
    ) -> None:
        """Record a purchase lot.

        total_amount is the actual amount charged (positive, in transaction currency).
        fx_rate: 1 EUR = fx_rate units of transaction currency.
        """
        total_eur = abs(total_amount) / fx_rate
        price_per_share_eur = total_eur / quantity
        self.lots[ticker].append(Lot(purchase_date, quantity, price_per_share_eur))

    def sell(
        self,
        ticker: str,
        quantity_sold: float,
        total_amount: float,
        fx_rate: float,
    ) -> tuple[float, float]:
        """Drain FIFO lots for a sale.

        total_amount is the actual amount received (positive for normal sells).
        Returns (cost_basis_eur, proceeds_eur).
        """
        # Delisted / worthless stocks may produce a tiny negative total; floor at 0.
        proceeds_eur = max(0.0, total_amount) / fx_rate

        cost_eur = 0.0
        remaining = quantity_sold

        while remaining > 1e-9:
            if not self.lots[ticker]:
                raise ValueError(
                    f"FIFO underflow for {ticker}: no remaining lots "
                    f"(tried to sell {quantity_sold} shares)"
                )
            lot = self.lots[ticker][0]
            consumed = min(lot.quantity, remaining)
            cost_eur += consumed * lot.price_per_share_eur
            lot.quantity -= consumed
            remaining -= consumed
            if lot.quantity < 1e-9:
                self.lots[ticker].popleft()

        return cost_eur, proceeds_eur
