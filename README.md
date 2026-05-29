# RevolutTaxCalculatorFr

Génère automatiquement votre déclaration fiscale française à partir de vos relevés Revolut.

## Fonctionnement

L'outil lit vos exports CSV Revolut et calcule les montants à reporter dans votre déclaration :

| Case | Formulaire | Description |
|------|-----------|-------------|
| **2DC** | 2042 | Dividendes bruts reçus |
| **2AB** | 2042 | Crédit d'impôt sur valeurs étrangères (retenue à la source) |
| **3VG** | 2042 + 2074 | Plus-values nettes de cession de valeurs mobilières |
| **3VH** | 2042 | Moins-values de l'année (reportables 10 ans) |

Le formulaire 2074 (détail des cessions) est inclus dans le rapport HTML.

## Fichiers d'entrée

Deux exports Revolut sont supportés :

1. **Relevé d'activité** *(obligatoire)* — export complet de toutes vos transactions.
   Dans l'app Revolut : *Investir → Portefeuille → ⋯ → Exporter*

2. **Document fiscal annuel** *(optionnel mais recommandé)* — résumé annuel des dividendes et cessions avec montants en euros.
   Dans l'app Revolut : *Investir → Portefeuille → ⋯ → Documents fiscaux*
   Lorsque ce fichier est fourni, ses montants EUR sont utilisés directement.
   Sans ce fichier, les retenues sont estimées via les taux conventionnels (voir ci-dessous).

## Installation

```bash
# Pré-requis : Python 3.12+ et uv (https://docs.astral.sh/uv/)
git clone <repo>
cd RevolutTaxCalculatorFr
uv sync
```

## Utilisation

```bash
uv run revolut-tax \
  --activity  relevé_activité.csv \
  --tax-doc   document_fiscal_2025.csv \   # optionnel
  --year      2025 \                       # défaut : année précédente
  --output    rapport_2025.html            # défaut : tax_report_YEAR.html
```

Le résumé s'affiche dans le terminal et un rapport HTML détaillé est enregistré.

## Taux de retenue à la source (fallback sans document fiscal)

| Pays / ISIN | Taux | Exemple |
|-------------|------|---------|
| États-Unis (convention France-US) | 15 % | AAPL, GOOGL, KO, O, NVDA |
| ADR taïwanais | 20 % | TSM (US8740391003) |
| Irlande | 0 % | VUSA, IQQQ |
| Royaume-Uni | 0 % | HSBC (US4042804066) |

## Méthode de calcul

- **Coût de revient** : méthode FIFO/PEPS (*Premier Entré, Premier Sorti*), conformément à l'article 150-0 A du CGI.
- **Conversion EUR** : taux de change fourni par Revolut pour chaque transaction (1 EUR = X devise).
- **Dividendes bruts** : reconstituéss depuis le montant net reçu via le taux de retenue conventionnel (si pas de document fiscal).

## Docker

```bash
# Mode web (défaut)
docker build -t revolut-tax-fr .
docker run -p 8080:8080 revolut-tax-fr
# Puis ouvrez http://localhost:8080 dans votre navigateur

# Mode CLI (override de l'entrypoint)
docker run --rm \
  -v "$(pwd)/data":/data \
  revolut-tax-fr \
  uv run revolut-tax \
  --activity /data/activity.csv \
  --year 2025 \
  --output /data/report.html
```

## Tests

```bash
uv run pytest
```

---

> ⚠️ Ce rapport est fourni à titre indicatif. Vérifiez les montants avec votre conseiller fiscal avant soumission.

---

# RevolutTaxCalculatorFr (English)

Automatically generates your French tax declaration from Revolut CSV exports.

## How it works

The tool reads your Revolut CSV exports and computes the amounts to report in your French tax return:

| Box | Form | Description |
|-----|------|-------------|
| **2DC** | 2042 | Gross dividends received |
| **2AB** | 2042 | Foreign tax credit (withholding tax) |
| **3VG** | 2042 + 2074 | Net capital gains from securities sales |
| **3VH** | 2042 | Capital losses for the year (10-year carry-forward) |

Form 2074 detail (per-transaction breakdown) is included in the HTML report.

## Input files

Two Revolut exports are supported:

1. **Activity statement** *(required)* — full export of all your transactions.
   In the Revolut app: *Invest → Portfolio → ⋯ → Export*

2. **Annual tax document** *(optional but recommended)* — annual summary of dividends and sales with EUR amounts already computed.
   In the Revolut app: *Invest → Portfolio → ⋯ → Tax documents*
   When provided, its EUR amounts are used directly.
   Without it, withholding taxes are estimated from treaty rates (see below).

## Installation

```bash
# Prerequisites: Python 3.12+ and uv (https://docs.astral.sh/uv/)
git clone <repo>
cd RevolutTaxCalculatorFr
uv sync
```

## Usage

```bash
uv run revolut-tax \
  --activity  activity_statement.csv \
  --tax-doc   tax_document_2025.csv \   # optional
  --year      2025 \                    # defaults to previous year
  --output    report_2025.html          # defaults to tax_report_YEAR.html
```

A summary is printed to the terminal and a detailed HTML report is saved.

## Withholding tax rates (fallback without tax document)

| Country / ISIN | Rate | Examples |
|----------------|------|---------|
| United States (France-US treaty) | 15% | AAPL, GOOGL, KO, O, NVDA |
| Taiwanese ADR | 20% | TSM (US8740391003) |
| Ireland | 0% | VUSA, IQQQ |
| United Kingdom | 0% | HSBC (US4042804066) |

## Calculation methodology

- **Cost basis**: FIFO (*First In, First Out* / PEPS) method, as required by French tax law (Article 150-0 A CGI).
- **EUR conversion**: exchange rate provided by Revolut per transaction (1 EUR = X currency units).
- **Gross dividends**: back-calculated from net received amount using the applicable withholding rate (fallback only).

## Docker

```bash
# Web mode (default)
docker build -t revolut-tax-fr .
docker run -p 8080:8080 revolut-tax-fr
# Then open http://localhost:8080 in your browser

# CLI mode (entrypoint override)
docker run --rm \
  -v "$(pwd)/data":/data \
  revolut-tax-fr \
  uv run revolut-tax \
  --activity /data/activity.csv \
  --year 2025 \
  --output /data/report.html
```

## Tests

```bash
uv run pytest
```

---

> ⚠️ This report is provided for informational purposes only. Verify all amounts with your tax advisor before submission.
