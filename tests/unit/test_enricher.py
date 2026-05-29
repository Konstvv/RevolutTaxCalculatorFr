"""Unit tests for the SecurityCache enricher."""

import json
import warnings

from revolut_tax_fr.enricher import SecurityCache, SecurityInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cache(tmp_path=None) -> SecurityCache:
    """Return a fresh in-memory cache (path=None skips disk I/O)."""
    return SecurityCache(path=tmp_path)


# ---------------------------------------------------------------------------
# Bootstrap seeding from config
# ---------------------------------------------------------------------------


def test_seed_from_config_known_ticker():
    cache = _make_cache()
    info = cache.get("AAPL")
    assert info is not None
    assert info.isin == "US0378331005"
    assert info.country == "US"
    assert info.source == "config"


def test_seed_from_config_hsbc_country_is_gb():
    """HSBC should have GB as domicile country (UK company), not US."""
    cache = _make_cache()
    info = cache.get("HSBC")
    assert info is not None
    assert info.country == "GB"


def test_seed_from_config_vusa_is_ireland():
    cache = _make_cache()
    info = cache.get("VUSA")
    assert info is not None
    assert info.country == "IE"


def test_seed_from_config_unknown_ticker_returns_none():
    cache = _make_cache()
    assert cache.get("UNKN") is None


# ---------------------------------------------------------------------------
# populate_from_tax_doc
# ---------------------------------------------------------------------------


_TAX_DOC_DIVS = [
    {
        "ticker": "AAPL",
        "security_name": "Apple Inc.",
        "isin": "US0378331005",
        "country": "US",
        "gross_eur": 0.47,
        "withholding_eur": 0.07,
        "net_eur": 0.40,
    },
    {
        "ticker": "NEWSTOCK",
        "security_name": "New Stock Corp.",
        "isin": "US9999999999",
        "country": "US",
        "gross_eur": 1.00,
        "withholding_eur": 0.15,
        "net_eur": 0.85,
    },
]


def test_populate_from_tax_doc_adds_new_ticker():
    cache = _make_cache()
    cache.populate_from_tax_doc([], _TAX_DOC_DIVS)
    info = cache.get("NEWSTOCK")
    assert info is not None
    assert info.isin == "US9999999999"
    assert info.source == "tax_doc"


def test_populate_from_tax_doc_upgrades_config_entry():
    """tax_doc entry should overwrite the config seed."""
    cache = _make_cache()
    assert cache.get("AAPL").source == "config"
    cache.populate_from_tax_doc([], _TAX_DOC_DIVS)
    assert cache.get("AAPL").source == "tax_doc"


def test_populate_from_tax_doc_from_sells():
    cache = _make_cache()
    sells = [
        {
            "ticker": "KO",
            "security_name": "Example Corp.",
            "isin": "US1912161007",
            "country": "US",
        }
    ]
    cache.populate_from_tax_doc(sells, [])
    info = cache.get("KO")
    assert info.isin == "US1912161007"
    assert info.source == "tax_doc"


def test_populate_from_tax_doc_persists_to_disk(tmp_path):
    cache_file = tmp_path / "securities.json"
    cache = SecurityCache(path=cache_file)
    cache.populate_from_tax_doc([], _TAX_DOC_DIVS)

    assert cache_file.exists()
    on_disk = json.loads(cache_file.read_text())
    assert "NEWSTOCK" in on_disk
    # Config seeds are NOT persisted — only tax_doc / yfinance entries.
    assert "AAPL" in on_disk  # AAPL got upgraded to tax_doc
    # A ticker that's config-only should not appear on disk.
    assert "GOOGL" not in on_disk


def test_populate_from_tax_doc_skips_empty_ticker():
    cache = _make_cache()
    cache.populate_from_tax_doc([], [{"ticker": "", "isin": "US0000000000"}])
    # Should not crash and not add an empty-string key.
    assert cache.get("") is None


# ---------------------------------------------------------------------------
# enrich — cache hit
# ---------------------------------------------------------------------------


def test_enrich_returns_tax_doc_entry_without_network():
    cache = _make_cache()
    cache.populate_from_tax_doc([], _TAX_DOC_DIVS)
    info = cache.enrich("NEWSTOCK")
    assert info.source == "tax_doc"
    assert info.isin == "US9999999999"


def test_enrich_returns_config_seed_without_network():
    """A ticker known from config should be returned without hitting yfinance."""
    cache = _make_cache()
    info = cache.enrich("AAPL")
    # Should return config entry (no network call made in unit tests).
    assert info.ticker == "AAPL"
    assert info.country == "US"


# ---------------------------------------------------------------------------
# enrich — yfinance mock
# ---------------------------------------------------------------------------


def test_enrich_calls_yfinance_for_unknown_ticker(monkeypatch):
    """For a ticker not in cache or config, enrich should try yfinance."""
    fetched = []

    def mock_fetch(ticker):
        fetched.append(ticker)
        return SecurityInfo(
            ticker=ticker,
            name="Mock Corp.",
            isin="US1234567890",
            country="US",
            source="yfinance",
        )

    monkeypatch.setattr("revolut_tax_fr.enricher._fetch_yfinance", mock_fetch)
    cache = _make_cache()
    info = cache.enrich("MOCK")
    assert info.source == "yfinance"
    assert info.isin == "US1234567890"
    assert "MOCK" in fetched


def test_enrich_yfinance_result_is_cached(monkeypatch):
    """A successful yfinance lookup should not be repeated on subsequent enrich()."""
    call_count = [0]

    def mock_fetch(ticker):
        call_count[0] += 1
        return SecurityInfo(ticker=ticker, isin="US1234567890", country="US", source="yfinance")

    monkeypatch.setattr("revolut_tax_fr.enricher._fetch_yfinance", mock_fetch)
    cache = _make_cache()
    cache.enrich("MOCK")
    cache.enrich("MOCK")
    assert call_count[0] == 1


def test_enrich_yfinance_not_called_for_tax_doc_entries(monkeypatch):
    """Tickers already enriched via tax_doc skip the yfinance call entirely."""
    fetched = []
    monkeypatch.setattr(
        "revolut_tax_fr.enricher._fetch_yfinance",
        lambda t: fetched.append(t) or None,
    )
    cache = _make_cache()
    cache.populate_from_tax_doc([], _TAX_DOC_DIVS)
    cache.enrich("AAPL")
    assert "AAPL" not in fetched


# ---------------------------------------------------------------------------
# enrich — fallback warning
# ---------------------------------------------------------------------------


def test_enrich_warns_for_truly_unknown_ticker(monkeypatch):
    monkeypatch.setattr("revolut_tax_fr.enricher._fetch_yfinance", lambda _: None)
    cache = _make_cache()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        info = cache.enrich("UNKN")
    assert info.source == "fallback"
    assert any("UNKN" in str(warning.message) for warning in w)


# ---------------------------------------------------------------------------
# Disk persistence round-trip
# ---------------------------------------------------------------------------


def test_cache_loads_from_disk(tmp_path):
    cache_file = tmp_path / "securities.json"

    # First run: populate and save.
    c1 = SecurityCache(path=cache_file)
    c1.populate_from_tax_doc([], _TAX_DOC_DIVS)

    # Second run: load from disk.
    c2 = SecurityCache(path=cache_file)
    info = c2.get("NEWSTOCK")
    assert info is not None
    assert info.source == "tax_doc"
    assert info.isin == "US9999999999"


def test_disk_entry_overrides_config_on_load(tmp_path):
    """A tax_doc entry on disk should win over the in-memory config seed."""
    cache_file = tmp_path / "securities.json"

    # Write a tax_doc entry for AAPL with a different ISIN.
    cache_file.write_text(
        json.dumps(
            {
                "AAPL": {
                    "ticker": "AAPL",
                    "name": "X",
                    "isin": "XX000000000",
                    "country": "XX",
                    "source": "tax_doc",
                }
            }
        )
    )

    cache = SecurityCache(path=cache_file)
    info = cache.get("AAPL")
    assert info.source == "tax_doc"
    assert info.isin == "XX000000000"
