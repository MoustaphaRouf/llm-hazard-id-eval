"""Phase 2 metrics: matching model hazards to human hazards, and agreement.

Matching is lexical (TF-IDF on word 1-2-grams, cosine similarity). It only
*proposes* correspondences; the decision on whether a model hazard is valid
and new belongs to the human adjudicators (see :mod:`hazid.adjudication`).
"""
from __future__ import annotations

import itertools
import re
import statistics
import unicodedata
from collections import defaultdict

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def normalise(text) -> str:
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def match(a: list[str], b: list[str], threshold: float) -> dict[int, tuple[int, float]]:
    """Best match in ``b`` for each item of ``a`` whose similarity reaches ``threshold``.

    Several items of ``a`` may map to the same item of ``b`` (no uniqueness).
    """
    if not a or not b:
        return {}
    corpus = [normalise(x) for x in a + b]
    try:
        m = TfidfVectorizer(ngram_range=(1, 2), min_df=1).fit_transform(corpus)
    except ValueError:  # empty vocabulary
        return {}
    sim = cosine_similarity(m[: len(a)], m[len(a):])
    out = {}
    for i in range(len(a)):
        j = int(sim[i].argmax())
        if sim[i][j] >= threshold:
            out[i] = (j, round(float(sim[i][j]), 3))
    return out


def jaccard(a: list[str], b: list[str], threshold: float) -> float:
    """Overlap of two hazard lists; intersection = min(matched a->b, matched b->a) keeps 0 <= J <= 1."""
    if not a or not b:
        return 0.0
    common = min(len(match(a, b, threshold)), len(match(b, a, threshold)))
    union = len(a) + len(b) - common
    return round(common / union, 3) if union else 0.0


def labels(run: dict) -> list[str]:
    return sorted({str(h.get("libelle", "")).strip() for h in run["hazards"] if h.get("libelle")})


def metrics(runs: list[dict], humans: dict[str, list[str]], threshold: float) -> pd.DataFrame:
    """One row per (dossier, model, condition).

    * ``recall_union``: share of human hazards matched by the union of all runs
      (what the original workbook reported). It grows with the number of runs.
    * ``recall_per_run``: mean share matched by a single run, the figure that
      corresponds to one consultation of the model.
    * ``novel_union``: model hazards (union of runs) with no human match:
      candidates for the adjudicators, not findings.
    * ``count_sd``: standard deviation of the number of hazards per run.
    * ``content_stability``: mean pairwise Jaccard between runs: do repeated
      runs propose the *same* hazards, not just as many?
    """
    groups = defaultdict(list)
    for r in runs:
        groups[(r["dossier"], r["model_key"], r["condition"])].append(r)
    rows = []
    for (did, key, cond), rs in sorted(groups.items()):
        h = humans.get(did, [])
        per_run = [labels(r) for r in rs]
        union = sorted(set().union(*per_run))
        counts = [len(x) for x in per_run]
        rows.append({
            "dossier": did, "model": key, "condition": cond, "runs": len(rs),
            "hazards_mean": round(sum(counts) / len(counts), 1),
            "count_sd": round(statistics.stdev(counts), 2) if len(counts) > 1 else 0.0,
            "human_hazards": len(h),
            "recall_union": round(len(match(h, union, threshold)) / len(h), 3) if h else None,
            "recall_per_run": (round(statistics.mean(len(match(h, x, threshold)) / len(h) for x in per_run), 3)
                               if h else None),
            "novel_union": len(union) - len(match(union, h, threshold)),
            "content_stability": (round(statistics.mean(jaccard(x, y, threshold)
                                                        for x, y in itertools.combinations(per_run, 2)), 3)
                                  if len(per_run) > 1 else None),
        })
    return pd.DataFrame(rows)


def agreement(runs: list[dict], threshold: float) -> pd.DataFrame:
    """Jaccard between each pair of models, per dossier and condition.

    * ``jaccard_union``: on the union of each model's runs (the original
      measure). Unions grow with repetitions and tend towards everything a
      model can say, so this agreement drifts upwards with the number of runs.
    * ``jaccard_per_run``: mean Jaccard over all pairs (run of model 1, run of
      model 2): the agreement of two single consultations.
    """
    by = defaultdict(lambda: defaultdict(list))
    for r in runs:
        by[(r["dossier"], r["condition"])][r["model_key"]].append(labels(r))
    rows = []
    for (did, cond), per_model in sorted(by.items()):
        for m1, m2 in itertools.combinations(sorted(per_model), 2):
            u1 = sorted(set().union(*per_model[m1]))
            u2 = sorted(set().union(*per_model[m2]))
            pairs = [jaccard(x, y, threshold) for x in per_model[m1] for y in per_model[m2]]
            rows.append({"dossier": did, "condition": cond, "pair": f"{m1} / {m2}",
                         "jaccard_union": jaccard(u1, u2, threshold),
                         "jaccard_per_run": round(statistics.mean(pairs), 3)})
    return pd.DataFrame(rows)


def calibration_table(runs: list[dict], humans: dict[str, list[str]], calibration_dossiers: list[str],
                      thresholds=(0.35, 0.45, 0.55, 0.65, 0.75)) -> pd.DataFrame:
    """Recall and novelty vs threshold, on the designated calibration files ONLY.

    The protocol says the threshold is fixed on two test files before the
    campaign results are examined. The original notebook scanned thresholds on
    all files, which would let the results inform the threshold; here the
    calibration set must be named explicitly and should then be excluded from
    the reported results.
    """
    rows = []
    for t in thresholds:
        found = total = novel = 0
        for did in calibration_dossiers:
            h = humans.get(did, [])
            m = sorted({x for r in runs if r["dossier"] == did for x in labels(r)})
            if not h or not m:
                continue
            total += len(h)
            found += len(match(h, m, t))
            novel += len(m) - len(match(m, h, t))
        rows.append({"threshold": t, "recall": round(found / total, 3) if total else None, "novel": novel})
    return pd.DataFrame(rows)
