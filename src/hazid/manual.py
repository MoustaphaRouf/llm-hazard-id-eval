"""Manual matching, assisted by ranking.

When the panel's hazards and the models' hazards are worded too differently
for lexical matching (e.g. verbatim panel text vs normalised model output),
matching is done by a person. To keep the work tractable, every model
formulation of a file is ranked against each panel hazard and only the top
``k`` candidates are shown. The ranking only orders candidates; the decision
"same hazard?" is the reviewer's.

Ranking uses a local multilingual sentence-embedding model when
``sentence-transformers`` is installed (nothing leaves the session), and falls
back to character n-gram TF-IDF otherwise.

Limitation: a match ranked below ``k`` is never shown, so recall is a lower
bound; report ``k`` with the results. The pilot used k = 10 and still found
matches at ranks 9-10, hence the default of 20.

The pilot also showed that similarity, lexical or semantic, does not replace
the reviewer: against the reviewer's judgement, embedding similarity reached
an AUC of 0.63 and no threshold exceeded 13 % precision.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from .matching import labels, normalise

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
# Review codes. The pilot showed that "partial" mixes two different cases, so they are coded apart:
#   Composante  - the model hazard isolates one component of a composite panel hazard
#                 (e.g. a report hazard "wind, QNH and QFE data erroneous" split by a model into
#                 "wind data erroneous" and "QNH/QFE measurement erroneous"): legitimate coverage;
#   Recouvrement - any other partial overlap (more general, different consequence...): incomplete.
# "Partiel" (pilot code) is still read, and treated as Composante + Recouvrement.
CHOICES = ("Oui", "Composante", "Recouvrement", "Non")
COMPONENT, OVERLAP, LEGACY_PARTIAL = "Composante", "Recouvrement", "Partiel"


def _similarity(a: list[str], b: list[str], method: str) -> np.ndarray:
    if method == "embeddings":
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(EMBEDDING_MODEL)
        ea = model.encode(a, normalize_embeddings=True)
        eb = model.encode(b, normalize_embeddings=True)
        return ea @ eb.T
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    x = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5)).fit_transform([normalise(t) for t in a + b])
    return cosine_similarity(x[: len(a)], x[len(a):])


def default_method() -> str:
    try:
        import sentence_transformers  # noqa: F401
        return "embeddings"
    except ImportError:
        return "char-ngrams"


def candidates(runs: list[dict], humans: dict[str, list[dict]], dossier: str, k: int = 20,
               method: str | None = None) -> pd.DataFrame:
    """Top-k model formulations for each panel hazard of ``dossier``.

    Which model proposed a formulation is deliberately not shown: the reviewer
    judges "same hazard?" without knowing the source.
    """
    method = method or default_method()
    who = defaultdict(set)
    for r in runs:
        if r["dossier"] == dossier:
            for lab in labels(r):
                who[lab].add(r["model_key"])
    model_labels = sorted(who)
    panel = humans.get(dossier, [])
    if not panel or not model_labels:
        return pd.DataFrame()
    sim = _similarity([h["libelle"] for h in panel], model_labels, method)
    rows = []
    for i, h in enumerate(panel):
        for rank, j in enumerate(np.argsort(-sim[i])[:k], 1):
            rows.append({"Dossier": dossier, "N° danger": h["reference"], "Danger du panel": h["libelle"],
                         "Rang": rank, "Proposition des modèles": model_labels[j],
                         "Similarité": round(float(sim[i, j]), 3),
                         "Même danger ?": ""})
    out = pd.DataFrame(rows)
    out.attrs["method"] = method
    return out


def write_review_sheet(table: pd.DataFrame, path: str | Path) -> None:
    """Excel review sheet (Times New Roman, black text, D9D9D9 headers, F2F2F2 panel column)."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Appariement"
    thin = Side(style="thin", color="808080")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    cols = list(table.columns)
    widths = {"Dossier": 10, "N° danger": 10, "Danger du panel": 48, "Rang": 6,
              "Proposition des modèles": 60, "Similarité": 11, "Même danger ?": 15}
    for c, name in enumerate(cols, 1):
        cell = ws.cell(row=1, column=c, value=name)
        cell.font = Font(name="Times New Roman", bold=True, color="000000")
        cell.fill = PatternFill("solid", fgColor="D9D9D9")
        cell.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
        cell.border = border
        ws.column_dimensions[openpyxl.utils.get_column_letter(c)].width = widths.get(name, 14)
    for r, row in enumerate(table.itertuples(index=False), 2):
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = Font(name="Times New Roman", color="000000")
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            cell.border = border
            if cols[c - 1] == "Danger du panel":
                cell.fill = PatternFill("solid", fgColor="F2F2F2")
    answer = openpyxl.utils.get_column_letter(cols.index("Même danger ?") + 1)
    dv = DataValidation(type="list", formula1='"' + ",".join(CHOICES) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{answer}2:{answer}{len(table) + 1}")
    ws.freeze_panes = "C2"
    wb.save(path)


def recall_from_review(review: pd.DataFrame, runs: list[dict], count_partial: bool | str = False) -> pd.DataFrame:
    """Per-run and union recall from the reviewer's answers.

    A panel hazard counts as found by a run if the run contains at least one
    formulation accepted for that hazard. Accepted codes:

    * ``count_partial=False``: "Oui" only (strict);
    * ``count_partial="component"``: "Oui" + "Composante" (the decomposition rule);
    * ``count_partial=True``: "Oui" + every partial code (broad).
    """
    if count_partial == "component":
        ok = {"Oui", COMPONENT}
    elif count_partial:
        ok = {"Oui", COMPONENT, OVERLAP, LEGACY_PARTIAL}
    else:
        ok = {"Oui"}
    review = review.copy()
    review["Même danger ?"] = review["Même danger ?"].astype(str).str.strip()
    good = review[review["Même danger ?"].isin(ok)]
    match = defaultdict(set)   # (dossier, panel no) -> accepted model formulations
    for _, r in good.iterrows():
        match[(r["Dossier"], r["N° danger"])].add(r["Proposition des modèles"])
    panel = review.groupby("Dossier")["N° danger"].unique().to_dict()
    unanswered = int((review["Même danger ?"].isin(["", "nan", "None"])).sum())
    rows = []
    for r in runs:
        d = r["dossier"]
        if d not in panel:
            continue
        labs = set(labels(r))
        found = sum(bool(match[(d, n)] & labs) for n in panel[d])
        rows.append({"dossier": d, "model": r["model_key"], "condition": r["condition"], "run": r["run"],
                     "panel_hazards": len(panel[d]), "found": found})
    per_run = pd.DataFrame(rows)
    if per_run.empty:
        return per_run
    union = []
    for (d, m, c), g in per_run.groupby(["dossier", "model", "condition"]):
        labs = set().union(*(set(labels(r)) for r in runs
                             if r["dossier"] == d and r["model_key"] == m and r["condition"] == c))
        union.append({"dossier": d, "model": m, "condition": c,
                      "recall_union": sum(bool(match[(d, n)] & labs) for n in panel[d]) / len(panel[d])})
    summary = (per_run.assign(recall=per_run["found"] / per_run["panel_hazards"])
               .groupby(["dossier", "model", "condition"])
               .agg(runs=("run", "count"), recall_per_run=("recall", "mean"), recall_sd=("recall", "std"))
               .reset_index()
               .merge(pd.DataFrame(union), on=["dossier", "model", "condition"]))
    summary = summary.round(3)
    summary.attrs["unanswered"] = unanswered
    return summary
