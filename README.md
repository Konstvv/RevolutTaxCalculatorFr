# RevolutTaxCalculatorFr

Génère automatiquement votre déclaration fiscale française à partir de vos relevés Revolut.

## Ce que l'outil produit

| Case | Formulaire | Description |
|------|-----------|-------------|
| **2DC** | 2042 | Dividendes bruts reçus |
| **2AB** | 2042 | Crédit d'impôt sur valeurs étrangères (retenue à la source) |
| **3VG** | 2042 + 2074 | Plus-values nettes de cession de valeurs mobilières |
| **3VH** | 2042 | Moins-values de l'année (reportables 10 ans) |

Le formulaire 2074 (détail des cessions) est inclus dans le rapport HTML.

## Fichiers à préparer depuis l'app Revolut

1. **Relevé d'activité** *(obligatoire)* — export CSV de toutes vos transactions.
   *Investir → Portefeuille → ⋯ → Exporter*

2. **Document fiscal annuel** *(recommandé)* — résumé annuel des dividendes et cessions en euros.
   *Investir → Portefeuille → ⋯ → Documents fiscaux*

## Lancer l'outil

**Prérequis :** Python 3.12+ et [uv](https://docs.astral.sh/uv/)

```bash
git clone <repo>
cd RevolutTaxCalculatorFr
uv sync
uv run revolut-tax-web
```

Ouvrez **http://localhost:8080**, déposez vos fichiers CSV et cliquez sur **Générer le rapport**.

## Via Docker

```bash
docker build -t revolut-tax-fr .
docker run -p 8080:8080 revolut-tax-fr
# Ouvrez http://localhost:8080

# Arrêter
docker stop <container-id>
```

---

> ⚠️ Ce rapport est fourni à titre indicatif. Vérifiez les montants avec votre conseiller fiscal avant soumission.

---

# RevolutTaxCalculatorFr (English)

Automatically generates your French tax declaration from Revolut CSV exports.

## What it produces

| Box | Form | Description |
|-----|------|-------------|
| **2DC** | 2042 | Gross dividends received |
| **2AB** | 2042 | Foreign tax credit (withholding tax) |
| **3VG** | 2042 + 2074 | Net capital gains from securities sales |
| **3VH** | 2042 | Capital losses for the year (10-year carry-forward) |

Form 2074 (per-transaction breakdown) is included in the HTML report.

## Files to prepare from the Revolut app

1. **Activity statement** *(required)* — CSV export of all your transactions.
   *Invest → Portfolio → ⋯ → Export*

2. **Annual tax document** *(recommended)* — annual summary of dividends and sales with EUR amounts.
   *Invest → Portfolio → ⋯ → Tax documents*

## Launch the tool

**Prerequisites:** Python 3.12+ and [uv](https://docs.astral.sh/uv/)

```bash
git clone <repo>
cd RevolutTaxCalculatorFr
uv sync
uv run revolut-tax-web
```

Open **http://localhost:8080**, upload your CSV files and click **Générer le rapport**.

## Via Docker

```bash
docker build -t revolut-tax-fr .
docker run -p 8080:8080 revolut-tax-fr
# Open http://localhost:8080

# Stop
docker stop <container-id>
```

---

> ⚠️ This report is provided for informational purposes only. Verify all amounts with your tax advisor before submission.
