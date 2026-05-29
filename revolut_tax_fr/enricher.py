from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_DEFAULT_CACHE_PATH = Path.home() / ".revolut_tax_fr" / "securities.json"

# Maps yfinance "country" string → ISO 3166-1 alpha-2 code.
_YFINANCE_COUNTRY_TO_ISO: dict[str, str] = {
    "Australia": "AU",
    "Austria": "AT",
    "Belgium": "BE",
    "Brazil": "BR",
    "Canada": "CA",
    "Cayman Islands": "KY",
    "China": "CN",
    "Denmark": "DK",
    "Finland": "FI",
    "France": "FR",
    "Germany": "DE",
    "Hong Kong": "HK",
    "India": "IN",
    "Ireland": "IE",
    "Israel": "IL",
    "Italy": "IT",
    "Japan": "JP",
    "Luxembourg": "LU",
    "Netherlands": "NL",
    "New Zealand": "NZ",
    "Norway": "NO",
    "Singapore": "SG",
    "South Korea": "KR",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Taiwan": "TW",
    "United Kingdom": "GB",
    "United States": "US",
}

# Priority order for source trustworthiness.
_SOURCE_PRIORITY = {"tax_doc": 3, "yfinance": 2, "config": 1, "fallback": 0}


@dataclass
class SecurityInfo:
    ticker: str
    name: str | None = None
    isin: str | None = None
    country: str | None = None  # ISO 2-letter domicile country
    source: str = "unknown"  # "tax_doc" | "yfinance" | "config" | "fallback"


class SecurityCache:
    """Two-layer security metadata cache.

    Layer 1 (in-memory, always): seeded from KNOWN_SECURITIES in config so the
    tool works out of the box for common stocks without any network calls.

    Layer 2 (on disk, ~/.revolut_tax_fr/securities.json): enriched entries from
    the Revolut annual tax document (highest trust) and Yahoo Finance lookups
    (network fallback). Disk entries survive across runs so yfinance is only
    queried once per unknown ticker.

    Priority: tax_doc > yfinance > config > fallback.
    """

    def __init__(self, path: Path | None = _DEFAULT_CACHE_PATH) -> None:
        self._path = path
        self._data: dict[str, SecurityInfo] = {}
        self._seed_from_config()
        if path is not None:
            self._load()  # disk entries override config seeds

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _seed_from_config(self) -> None:
        """Bootstrap with KNOWN_SECURITIES so common tickers work without a tax doc."""
        from .config import KNOWN_SECURITIES

        for ticker, (name, isin, country) in KNOWN_SECURITIES.items():
            self._data[ticker] = SecurityInfo(
                ticker=ticker, name=name, isin=isin, country=country, source="config"
            )

    def _load(self) -> None:
        if not self._path or not self._path.exists():
            return
        raw: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
        for ticker, fields in raw.items():
            entry = SecurityInfo(**fields)
            # Disk entry wins over config seed only if it carries equal or higher trust.
            existing = self._data.get(ticker)
            if not existing or _SOURCE_PRIORITY.get(entry.source, 0) >= _SOURCE_PRIORITY.get(
                existing.source, 0
            ):
                self._data[ticker] = entry

    def _save(self) -> None:
        if self._path is None:
            return
        # Only persist tax_doc and yfinance entries — config seeds are always re-applied
        # at startup, so storing them would just bloat the file.
        to_persist = {
            k: asdict(v) for k, v in self._data.items() if v.source in ("tax_doc", "yfinance")
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(to_persist, indent=2, default=str), encoding="utf-8")

    def _write(self, ticker: str, info: SecurityInfo) -> None:
        existing = self._data.get(ticker)
        if not existing or _SOURCE_PRIORITY.get(info.source, 0) >= _SOURCE_PRIORITY.get(
            existing.source, 0
        ):
            self._data[ticker] = info

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, ticker: str) -> SecurityInfo | None:
        """Return cached info without triggering any network call."""
        return self._data.get(ticker)

    def populate_from_tax_doc(
        self,
        sells: list[dict],
        dividends: list[dict],
    ) -> None:
        """Ingest ISIN + country from every entry in the Revolut annual tax document.

        The tax document is the most reliable source: Revolut provides the exact
        ISIN and country code used in the filing. These feed directly into
        withholding_rate(), where ISIN-level overrides handle ADR edge cases
        (e.g. HSBC country="US" in the doc, but ISIN override gives 0 %).
        """
        for entry in (*dividends, *sells):
            ticker = (entry.get("ticker") or "").strip()
            if not ticker:
                continue
            info = SecurityInfo(
                ticker=ticker,
                name=entry.get("security_name") or None,
                isin=entry.get("isin") or None,
                country=entry.get("country") or None,
                source="tax_doc",
            )
            self._write(ticker, info)
        self._save()

    def enrich(self, ticker: str) -> SecurityInfo:
        """Return security info, fetching from Yahoo Finance if not already cached.

        Falls back to a warning + empty info if yfinance is unavailable or
        the ticker is not found. The fallback is safe: withholding_rate() treats
        unknown securities as 0 % withholding (conservative — user pays more
        French tax rather than claiming a credit they didn't earn).
        """
        cached = self._data.get(ticker)
        # Already enriched via tax_doc or yfinance — return immediately.
        if cached and cached.source in ("tax_doc", "yfinance"):
            return cached

        # Try yfinance (network call, cached after first successful fetch).
        info = _fetch_yfinance(ticker)
        if info:
            self._write(ticker, info)
            self._save()
            return info

        # Keep existing config seed if present, but emit a warning so the user
        # knows the data came from the built-in table, not a live source.
        if cached and cached.source == "config":
            return cached

        warnings.warn(
            f"Unknown security '{ticker}': ISIN and country could not be determined. "
            "Withholding rate defaulting to 0 %. Provide the Revolut annual tax "
            "document for accurate results, or run once with --year for a year that "
            "has a tax document to populate the cache.",
            stacklevel=3,
        )
        fallback = SecurityInfo(ticker=ticker, source="fallback")
        self._data[ticker] = fallback
        return fallback


# ------------------------------------------------------------------
# Yahoo Finance helpers
# ------------------------------------------------------------------


def _fetch_yfinance(ticker: str) -> SecurityInfo | None:
    try:
        import yfinance as yf
    except ImportError:
        return None

    try:
        t = yf.Ticker(ticker)
        info: dict[str, Any] = t.info or {}

        # yfinance returns a minimal dict for unknown tickers.
        if not info or (info.get("quoteType") in ("NONE", None) and not info.get("longName")):
            return None

        raw_isin = getattr(t, "isin", None)
        isin = (
            str(raw_isin).strip()
            if raw_isin and str(raw_isin).strip() not in ("nan", "None", "")
            else None
        )

        raw_country = info.get("country") or ""
        country = _YFINANCE_COUNTRY_TO_ISO.get(raw_country)

        name = info.get("longName") or info.get("shortName") or None

        if not name and not isin and not country:
            return None

        return SecurityInfo(
            ticker=ticker,
            name=name,
            isin=isin,
            country=country,
            source="yfinance",
        )
    except Exception:
        return None
