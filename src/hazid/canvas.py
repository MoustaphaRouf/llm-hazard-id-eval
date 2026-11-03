"""The study canvas: one workbook holding every safety-assessment file.

Sheet ``A_Contexte_pre_seance``: one row per file (``ID dossier``) with the
information available to the panel *before* the hazard-identification
session. Sheet ``B_Dangers``: the hazards the human panel identified, one row
per hazard, with ``N° danger`` and ``Reformulation normalisée`` (the hazard
rewritten in the normalised « event leading to consequence » form).

The canvas must be anonymised before use: file identifiers only (EDS-01...),
no centre or participant names.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ID = "ID dossier"
HAZARD_NO = "N° danger"
HAZARD_TEXT = "Reformulation normalisée"
# Columns of sheet A that are bookkeeping, not context, and are never sent to a model.
NOT_CONTEXT = {ID, "Contrôle anti-contamination effectué", "Observations"}
SHEET_CONTEXT = "A_Contexte_pre_seance"
SHEET_HAZARDS = "B_Dangers"


@dataclass
class Dossier:
    id: str
    context: str
    human_hazards: list[dict] = field(default_factory=list)  # {"reference", "libelle"}

    @property
    def human_labels(self) -> list[str]:
        return [h["libelle"] for h in self.human_hazards]


def _header_and_rows(sheet):
    """Locate the header row (first cell ``ID dossier``); data starts right after it."""
    rows = list(sheet.iter_rows(values_only=True))
    for i, row in enumerate(rows):
        if row and row[0] == ID:
            return list(row), rows[i + 1:]
    raise ValueError(f"header '{ID}' not found in sheet '{sheet.title}'")


def load_canvas(path: str | Path, hazard_column: str = HAZARD_TEXT, skip_examples: bool = True) -> dict[str, Dossier]:
    """Load every file of the canvas.

    ``hazard_column`` selects the panel's formulation: the normalised one by
    default (the protocol), or e.g. ``"Libellé du danger (verbatim)"``; any
    deviation from the protocol must be recorded in the study log. Rows whose
    identifier contains "exemple" (the filled-in example row) are skipped.
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    head_a, rows_a = _header_and_rows(wb[SHEET_CONTEXT])
    dossiers = {}
    for row in rows_a:
        if not row or not row[0] or (skip_examples and "exemple" in str(row[0]).lower()):
            continue
        fields = [f"{head_a[i]} : {v}" for i, v in enumerate(row)
                  if v not in (None, "") and head_a[i] not in NOT_CONTEXT]
        dossiers[row[0]] = Dossier(row[0], "\n".join(fields))

    head_b, rows_b = _header_and_rows(wb[SHEET_HAZARDS])
    i_no, i_txt = head_b.index(HAZARD_NO), head_b.index(hazard_column)
    for row in rows_b:
        if row and row[0] in dossiers and row[i_txt]:
            dossiers[row[0]].human_hazards.append({"reference": row[i_no], "libelle": str(row[i_txt])})
    return dossiers


def write_canvas(dossiers: list[dict], path: str | Path, context_fields: list[str]) -> None:
    """Write a canvas from plain dicts (used for the fictional example).

    Each dict: ``{"id": ..., <context field>: ..., "hazards": [(no, text), ...]}``.
    """
    import openpyxl

    wb = openpyxl.Workbook()
    a = wb.active
    a.title = SHEET_CONTEXT
    a.append([ID, *context_fields, "Contrôle anti-contamination effectué", "Observations"])
    b = wb.create_sheet(SHEET_HAZARDS)
    b.append([ID, HAZARD_NO, HAZARD_TEXT])
    for d in dossiers:
        a.append([d["id"], *[d.get(f, "") for f in context_fields], "Oui", ""])
        for no, text in d.get("hazards", []):
            b.append([d["id"], no, text])
    wb.save(path)
