from __future__ import annotations

# Withholding tax rates applied at source before the dividend reaches the investor.
# Keys are ISIN strings for special-case overrides; country codes are the fallback.
WITHHOLDING_RATES_BY_ISIN: dict[str, float] = {
    "US8740391003": 0.20,  # TSM — Taiwanese company, US-listed ADR
    "US4042804066": 0.00,  # HSBC — UK company (ADR), UK imposes no dividend withholding
}

WITHHOLDING_RATES_BY_COUNTRY: dict[str, float] = {
    "US": 0.15,  # France-US tax treaty (assumes W-8BEN filed with broker)
    "IE": 0.00,  # Ireland-domiciled ETFs distribute without withholding
    "GB": 0.00,  # UK companies — UK imposes no dividend withholding tax
    "TW": 0.20,  # Taiwan — no France-Taiwan treaty; standard 20 % non-resident rate
    "KY": 0.00,  # Cayman Islands — no dividend withholding tax
    "HK": 0.00,  # Hong Kong — no dividend withholding tax
    "SG": 0.00,  # Singapore — no dividend withholding tax
    "LU": 0.15,  # Luxembourg — France-Luxembourg treaty
    "NL": 0.15,  # Netherlands — France-Netherlands treaty
    "DE": 0.15,  # Germany — France-Germany treaty
    "JP": 0.10,  # Japan — France-Japan treaty
    "CH": 0.15,  # Switzerland — France-Switzerland treaty
    "CA": 0.15,  # Canada — France-Canada treaty
}


def withholding_rate(isin: str | None, country: str | None) -> float:
    if isin and isin in WITHHOLDING_RATES_BY_ISIN:
        return WITHHOLDING_RATES_BY_ISIN[isin]
    if country and country in WITHHOLDING_RATES_BY_COUNTRY:
        return WITHHOLDING_RATES_BY_COUNTRY[country]
    return 0.0
