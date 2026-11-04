"""Blind adjudication workbook.

Human and model hazards are mixed, their origin hidden and their order
shuffled with a fixed seed. Adjudicators judge each one (valid? already
covered? operational relevance?) without knowing who proposed it. The key
(origin of each line) is written to a separate sheet that is removed from the
file sent to the adjudicators. No model ever grades its own output.

Model hazards from the same file are de-duplicated on their normalised text.
Optionally (``collapse_threshold``), near-duplicates are also merged before
adjudication: with 3 models x 2 conditions x 5 runs, exact de-duplication
alone can leave several hundred lines per file, many of them paraphrases.
Merged lines keep the list of models that converged on them in the key.
"""
from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

from .matching import match, normalise

FONT, BLACK, GREY_HEADER, GREY_2 = "Times New Roman", "000000", "D9D9D9", "F2F2F2"
ORIGIN_HUMAN = "humain"


def build_lot(runs: list[dict], humans: dict[str, list[dict]], collapse_threshold: float | None = None):
    """Return the shuffled-to-be list of (dossier, label, origin, source ref, condition, n_models)."""
    lot = [(did, h["libelle"], ORIGIN_HUMAN, h["reference"], "-", "-")
           for did, hs in sorted(humans.items()) for h in hs]
    models_for = defaultdict(set)   # (dossier, normalised label) -> model keys
    first = {}                      # (dossier, normalised label) -> (label, origin, ref, condition)
    for r in runs:
        for h in r["hazards"]:
            lab = str(h.get("libelle", "")).strip()
            if not lab:
                continue
            k = (r["dossier"], normalise(lab))
            models_for[k].add(r["model_key"])
            first.setdefault(k, (lab, f"modele_{r['model_key']}", h.get("reference", ""), r["condition"]))
    per_dossier = defaultdict(list)
    for (did, _), (lab, origin, ref, cond) in first.items():
        per_dossier[did].append([lab, origin, ref, cond, set(models_for[(did, normalise(lab))])])
    for did, items in sorted(per_dossier.items()):
        if collapse_threshold is not None:
            items = _collapse(items, collapse_threshold)
        lot += [(did, lab, origin, ref, cond, len(ms)) for lab, origin, ref, cond, ms in items]
    return lot


def _collapse(items, threshold):
    """Greedy merge of near-duplicate model hazards (first occurrence kept)."""
    kept = []
    for it in items:
        m = match([it[0]], [k[0] for k in kept], threshold) if kept else {}
        if m:
            kept[m[0][0]][4] |= it[4]
        else:
            kept.append(it)
    return kept


def sample_lot(lot, max_model_per_dossier: int, seed: int):
    """Keep every panel hazard and a random sample of model hazards per file.

    The pilot produced 908 lines for two files, far too many for peer
    adjudicators. Panel hazards are all kept (they are the reference the
    adjudicators implicitly compare against, and they keep the origin hidden);
    model hazards are sampled uniformly, with a fixed seed, so the validity
    rate estimated on the sample applies to all model hazards of the file.
    """
    rng = random.Random(seed)
    humans = [x for x in lot if x[2] == ORIGIN_HUMAN]
    by_dossier = {}
    for x in lot:
        if x[2] != ORIGIN_HUMAN:
            by_dossier.setdefault(x[0], []).append(x)
    models = []
    for did in sorted(by_dossier):
        items = by_dossier[did]
        models += items if len(items) <= max_model_per_dossier else rng.sample(items, max_model_per_dossier)
    return humans + models


def write_workbook(runs, humans, path: str | Path, seed: int, collapse_threshold: float | None = None,
                   max_model_per_dossier: int | None = None) -> int:
    """Write the full workbook (Adjudication + key); return the number of lines.

    ``max_model_per_dossier`` samples model hazards (see :func:`sample_lot`);
    the sampling seed is ``seed`` as well, so the workbook is reproducible.
    """
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    thin = Side(style="thin", color="808080")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def style(c, bold=False, fill=None, center=False):
        c.font = Font(name=FONT, size=11, bold=bold, color=BLACK)
        c.border = border
        c.alignment = Alignment(wrap_text=True, vertical="center" if center else "top",
                                horizontal="center" if center else None)
        if fill:
            c.fill = PatternFill("solid", fgColor=fill)

    lot = build_lot(runs, humans, collapse_threshold)
    if max_model_per_dossier is not None:
        lot = sample_lot(lot, max_model_per_dossier, seed)
    random.Random(seed).shuffle(lot)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Adjudication"
    ws.sheet_view.showGridLines = False
    heads = ["Réf. aveugle", "Dossier", "Libellé du danger", "Ce danger est-il valide ?",
             "Est-il déjà couvert par un autre ?", "Pertinence opérationnelle", "Commentaire de l'adjudicateur"]
    ws.cell(row=1, column=1, value="ADJUDICATION EN AVEUGLE — l'origine de chaque danger est masquée. "
                                    "Ne pas chercher à l'identifier.")
    style(ws.cell(row=1, column=1), bold=True, fill=GREY_2)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(heads))
    for i, (h, w) in enumerate(zip(heads, [13, 11, 62, 22, 26, 20, 40]), 1):
        style(ws.cell(row=2, column=i, value=h), bold=True, fill=GREY_HEADER, center=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[2].height = 44

    key_rows = []
    for k, (did, lab, origin, ref, cond, n_models) in enumerate(lot, 1):
        ref_blind = f"X-{k:04d}"
        for i, v in enumerate([ref_blind, did, lab, "", "", "", ""], 1):
            style(ws.cell(row=k + 2, column=i, value=v), fill=GREY_2 if i <= 2 else None)
        key_rows.append((ref_blind, did, origin, ref, cond, n_models, lab))
    last = len(lot) + 2
    for col, choices in [("D", '"Oui,Non,Douteux"'), ("E", '"Non — distinct,Oui — doublon,Partiellement"'),
                         ("F", '"Élevée,Moyenne,Faible,Non applicable"')]:
        dv = DataValidation(type="list", formula1=choices, allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{col}3:{col}{last}")
    ws.freeze_panes = "C3"

    wk = wb.create_sheet("Clé — NE PAS OUVRIR")
    for i, (h, w) in enumerate(zip(["Réf. aveugle", "Dossier", "Origine", "Réf. source", "Condition",
                                    "Nb modèles", "Libellé"], [13, 11, 16, 14, 14, 12, 62]), 1):
        style(wk.cell(row=1, column=i, value=h), bold=True, fill=GREY_HEADER, center=True)
        wk.column_dimensions[get_column_letter(i)].width = w
    for r, row in enumerate(key_rows, 2):
        for i, v in enumerate(row, 1):
            style(wk.cell(row=r, column=i, value=v), fill=GREY_2 if i <= 2 else None)
    wb.save(path)
    return len(lot)


def export_for_adjudicators(full_path: str | Path, out_path: str | Path) -> None:
    """Copy of the workbook with the Adjudication sheet only (no key)."""
    import openpyxl

    wb = openpyxl.load_workbook(full_path)
    for name in list(wb.sheetnames):
        if name != "Adjudication":
            del wb[name]
    wb.save(out_path)
