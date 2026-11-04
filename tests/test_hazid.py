import json
import pandas as pd

import openpyxl
import pytest

from hazid import adjudication, canvas, contamination, example, generation, matching
from hazid.canvas import Dossier
from hazid.protocol import Protocol, build_prompt


def mocks():
    return {"anthropic": example.mock_provider(), "openai": example.mock_provider(), "google": example.mock_provider()}


@pytest.fixture(scope="module")
def campaign(tmp_path_factory):
    out = tmp_path_factory.mktemp("runs")
    ds = example.dossiers()
    counts = generation.run_campaign(ds, Protocol(match_threshold=0.45), out, providers=mocks(), pause_s=0)
    return ds, out, counts


def test_canvas_round_trip_keeps_first_row(tmp_path):
    # Regression for B-3: the first file right after the header row must be read.
    path = tmp_path / "canvas.xlsx"
    canvas.write_canvas(example.DOSSIERS, path, example.CONTEXT_FIELDS)
    loaded = canvas.load_canvas(path)
    assert sorted(loaded) == ["FIC-01", "FIC-02"]
    assert loaded["FIC-01"].human_labels == example.dossiers()["FIC-01"].human_labels
    assert "Contrôle anti-contamination" not in loaded["FIC-01"].context


def test_extract_json_handles_fences_and_text():
    assert generation.extract_json('```json\n{"dangers": []}\n```') == {"dangers": []}
    assert generation.extract_json('Voici : {"dangers": [1]} fin') == {"dangers": [1]}
    with pytest.raises(ValueError):
        generation.extract_json("pas de json")


def test_campaign_counts_and_resume(campaign, tmp_path):
    ds, out, counts = campaign
    assert counts == {"run": 2 * 2 * 3 * 5, "failed": 0, "skipped": 0}
    again = generation.run_campaign(ds, Protocol(), out, providers=mocks(), pause_s=0)
    assert again["run"] == 0 and again["skipped"] == 60
    run = json.loads(next(out.glob("*.json")).read_text(encoding="utf-8"))
    assert run["protocol_fingerprint"] and run["prompt_fingerprint"]


def test_challenger_skipped_without_human_list(tmp_path):
    d = {"X": Dossier("X", "contexte quelconque", [])}
    counts = generation.run_campaign(d, Protocol(n_runs=1), tmp_path, providers=mocks(), pause_s=0)
    assert counts["run"] == 3  # blind only, one run per model
    with pytest.raises(ValueError):
        build_prompt("challenger", "ctx", [])


def test_failed_runs_are_archived(tmp_path):
    class Broken:
        def complete(self, *a):
            return "not json"
    d = {"X": Dossier("X", "ctx", [])}
    counts = generation.run_campaign(d, Protocol(n_runs=1), tmp_path, conditions=("blind",), keys=["A"],
                                     providers={"anthropic": Broken()}, pause_s=0)
    assert counts["failed"] == 1
    assert generation.load_runs(tmp_path) == []
    assert generation.load_runs(tmp_path, ok_only=False)[0]["status"] == "failed"
    # On resume, the failed run is retried (not skipped) and replaced when it succeeds.
    class Fixed:
        def complete(self, *a):
            return '{"dangers": [{"libelle": "x"}]}'
    again = generation.run_campaign(d, Protocol(n_runs=1), tmp_path, conditions=("blind",), keys=["A"],
                                    providers={"anthropic": Fixed()}, pause_s=0)
    assert again["run"] == 1 and again["skipped"] == 0
    assert generation.load_runs(tmp_path)[0]["n_hazards"] == 1


def test_protocol_flags_moving_aliases():
    p = Protocol(match_threshold=0.5)
    p.models["C"]["model"] = "gemini-pro-latest"
    assert any("moving alias" in w for w in p.warnings())
    assert Protocol(match_threshold=0.5).warnings() == []


def test_jaccard_bounded_with_many_to_one_matches():
    a = ["perte radio conduisant a perte de contact", "perte radio conduisant a perte du contact"]
    b = ["perte radio conduisant a perte de contact"]
    assert 0 <= matching.jaccard(a, b, 0.5) <= 1


def test_contamination_flags_leaked_hazard():
    leaked = Dossier("X", "Le dossier évoque une déviation latérale par un équipage non qualifié RNAV",
                     [{"reference": "H-1", "libelle": "Équipage non qualifié RNAV conduisant à une déviation latérale"}])
    assert contamination.check({"X": leaked})
    assert contamination.check(example.dossiers()) == []


def test_metrics_and_agreement(campaign):
    ds, out, _ = campaign
    runs = generation.load_runs(out)
    humans = {k: v.human_labels for k, v in ds.items()}
    m = matching.metrics(runs, humans, 0.45)
    assert len(m) == 12
    assert (m["recall_union"] >= m["recall_per_run"]).all()
    assert m["content_stability"].between(0, 1).all()
    a = matching.agreement(runs, 0.45)
    assert a[["jaccard_union", "jaccard_per_run"]].stack().between(0, 1).all()
    cal = matching.calibration_table(runs, humans, ["FIC-01"])
    assert list(cal["threshold"]) == [0.35, 0.45, 0.55, 0.65, 0.75]


def test_adjudication_is_blind_and_reproducible(campaign, tmp_path):
    ds, out, _ = campaign
    runs = generation.load_runs(out)
    humans = {k: v.human_hazards for k, v in ds.items()}
    full, sent = tmp_path / "full.xlsx", tmp_path / "sent.xlsx"
    n = adjudication.write_workbook(runs, humans, full, seed=1)
    n_humans = sum(len(v) for v in humans.values())
    n_model = len({(r["dossier"], matching.normalise(h["libelle"])) for r in runs for h in r["hazards"]})
    assert n == n_humans + n_model
    adjudication.export_for_adjudicators(full, sent)
    assert openpyxl.load_workbook(sent).sheetnames == ["Adjudication"]
    sheet = openpyxl.load_workbook(sent)["Adjudication"]
    visible = {c.value for row in sheet.iter_rows() for c in row if c.value}
    assert not any(str(v).startswith("modele_") or v == "humain" for v in visible)
    order = lambda p: [r[2] for r in openpyxl.load_workbook(p)["Adjudication"].iter_rows(min_row=3, values_only=True)]
    adjudication.write_workbook(runs, humans, tmp_path / "again.xlsx", seed=1)
    assert order(full) == order(tmp_path / "again.xlsx")


def test_collapse_merges_near_duplicates():
    runs = [{"dossier": "X", "model_key": k, "condition": "blind",
             "hazards": [{"libelle": t}]} for k, t in
            [("A", "Coupure radio pendant la bascule conduisant à une perte de contact"),
             ("B", "Coupure radio lors de la bascule conduisant à une perte de contact")]]
    assert len(adjudication.build_lot(runs, {}, None)) == 2
    lot = adjudication.build_lot(runs, {}, collapse_threshold=0.5)
    assert len(lot) == 1 and lot[0][5] == 2   # merged, two models converged


def test_canvas_skips_example_row_and_selects_column(tmp_path):
    path = tmp_path / "c.xlsx"
    rows = [dict(example.DOSSIERS[0], id="EDS-00 (exemple)"), example.DOSSIERS[1]]
    canvas.write_canvas(rows, path, example.CONTEXT_FIELDS)
    assert sorted(canvas.load_canvas(path)) == ["FIC-02"]
    with pytest.raises(ValueError):
        canvas.load_canvas(path, hazard_column="Colonne absente")


def test_provider_reuses_one_client():
    from hazid.providers import GoogleProvider
    made = []
    class P(GoogleProvider):
        def _make_client(self):
            made.append(1)
            return object()
    p = P()
    assert p._client() is p._client() and len(made) == 1


def test_anthropic_requires_default_temperature():
    from hazid.providers import AnthropicProvider
    with pytest.raises(ValueError):
        AnthropicProvider().complete("claude-sonnet-4-6", "s", "p", 0.7, 100)
    assert any("1.0" in w for w in Protocol(temperature=0.7, match_threshold=0.5).warnings())


def test_manual_review_round_trip(campaign, tmp_path):
    from hazid import manual
    ds, out, _ = campaign
    runs = generation.load_runs(out)
    humans = {k: v.human_hazards for k, v in ds.items()}
    table = manual.candidates(runs, humans, "FIC-01", k=5, method="char-ngrams")
    assert len(table) == 5 * len(humans["FIC-01"])
    path = tmp_path / "review.xlsx"
    manual.write_review_sheet(table, path)
    review = pd.read_excel(path, dtype={"Même danger ?": object})
    # Reviewer accepts the best candidate of every panel hazard.
    review.loc[review["Rang"] == 1, "Même danger ?"] = "Oui"
    res = manual.recall_from_review(review, runs)
    assert set(res["condition"]) == {"blind", "challenger"}
    assert res["recall_per_run"].between(0, 1).all()
    assert (res["recall_union"] >= res["recall_per_run"]).all()
    none = review.assign(**{"Même danger ?": "Non"})
    assert (manual.recall_from_review(none, runs)["recall_union"] == 0).all()


def test_partial_codes_and_legacy(campaign, tmp_path):
    from hazid import manual
    ds, out, _ = campaign
    runs = generation.load_runs(out)
    humans = {k: v.human_hazards for k, v in ds.items()}
    t = manual.candidates(runs, humans, "FIC-01", k=3, method="char-ngrams")
    t["Même danger ?"] = "Non"
    t.loc[t["Rang"] == 1, "Même danger ?"] = "Composante"
    t.loc[t["Rang"] == 2, "Même danger ?"] = "Recouvrement"
    strict = manual.recall_from_review(t, runs)
    comp = manual.recall_from_review(t, runs, count_partial="component")
    broad = manual.recall_from_review(t, runs, count_partial=True)
    assert (strict["recall_union"] == 0).all()
    assert (comp["recall_union"] <= broad["recall_union"]).all() and comp["recall_union"].sum() > 0
    legacy = t.replace({"Composante": "Partiel", "Recouvrement": "Partiel"})
    assert manual.recall_from_review(legacy, runs, count_partial=True)["recall_union"].equals(broad["recall_union"])


def test_adjudication_sampling_keeps_panel_and_caps_models(campaign, tmp_path):
    ds, out, _ = campaign
    runs = generation.load_runs(out)
    humans = {k: v.human_hazards for k, v in ds.items()}
    full = adjudication.build_lot(runs, humans)
    small = adjudication.sample_lot(full, 3, seed=1)
    n_h = sum(len(v) for v in humans.values())
    assert sum(x[2] == "humain" for x in small) == n_h
    assert len(small) == n_h + 3 * len(humans)
    assert small == adjudication.sample_lot(full, 3, seed=1)
    n = adjudication.write_workbook(runs, humans, tmp_path / "s.xlsx", seed=1, max_model_per_dossier=3)
    assert n == len(small)
