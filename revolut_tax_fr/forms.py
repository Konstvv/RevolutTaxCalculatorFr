from __future__ import annotations

from dataclasses import dataclass

from .calculator import TaxReport


@dataclass
class FormField:
    code: str
    label_fr: str
    value: float
    note: str


def build_form_2042(report: TaxReport) -> list[FormField]:
    return [
        FormField(
            code="2DC",
            label_fr="Dividendes et distributions",
            value=report.box_2dc,
            note="Montant brut des dividendes reçus (avant retenue à la source étrangère).",
        ),
        FormField(
            code="2AB",
            label_fr="Crédit d'impôt sur valeurs étrangères",
            value=report.box_2ab,
            note="Retenue à la source prélevée à l'étranger — à reporter telle quelle. "
            "Imputable sur l'impôt français dans la limite du crédit conventionnel.",
        ),
        FormField(
            code="3VG",
            label_fr="Plus-values et gains en capital (taux 12,8 %)",
            value=report.box_3vg,
            note="Plus-values nettes de cession de valeurs mobilières (si positives). "
            "Soumises au PFU de 12,8 % + prélèvements sociaux 17,2 % = 30 %.",
        ),
        FormField(
            code="3VH",
            label_fr="Moins-values de l'année imputables sur les 10 années suivantes",
            value=report.box_3vh,
            note="Pertes nettes de l'année, reportables pendant 10 ans sur des plus-values "
            "de même nature. Ne réduit pas directement l'impôt de l'année.",
        ),
    ]
