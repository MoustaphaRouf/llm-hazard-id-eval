# LLMs in ATM hazard identification: a retrospective evaluation protocol

[![tests](https://github.com/MoustaphaRouf/llm-hazard-id-eval/actions/workflows/ci.yml/badge.svg)](https://github.com/MoustaphaRouf/llm-hazard-id-eval/actions/workflows/ci.yml)

Before an air traffic management change goes live (a new procedure, a new system, a room
transfer), a panel of experts identifies the hazards it introduces (Functional Hazard Assessment,
FHA) and the mitigations they require (Preliminary System Safety Assessment, PSSA). Could a
language model take part in that session usefully? Would it find hazards the panel missed, or only
plausible-sounding ones? Would it say the same thing twice?

This repository holds the protocol and the tooling for answering those questions
**retrospectively**, on safety assessments that were already completed without AI. New sessions
with a model in the room cannot be organised, so the model is placed, after the fact, in the
panel's situation: same information, same task.

## Design

| Element | Choice | Why |
|---|---|---|
| Unit | one completed safety-assessment file | the panel's hazard list is the reference |
| Blind condition | the model sees only the pre-session context | can it do the panel's job? |
| Challenger condition | the model also sees the panel's hazards and must find what is missing | can it complement the panel? |
| Models | three providers, exact versions frozen | results should not be one vendor's artefact |
| Repetitions | 5 runs at temperature 1.0 (the only value current Anthropic APIs accept, used for all models) | a hazard that appears once in five runs is not the same evidence as one that appears every time |
| Anti-contamination | automatic lexical check + manual check | no panel hazard may leak into the blind context |
| Matching | by a reviewer, on the top 20 candidates per panel hazard ranked by a local embedding model, model identity hidden; codes *same / component / overlap / different* | the pilot showed that similarity, lexical or semantic, cannot decide whether two formulations name the same hazard |
| Judgement | blind adjudication by peers who do not know the files: panel and model hazards mixed, origin hidden | no model grades its own output, and the study lead does not adjudicate |
| Reproducibility | prompt and protocol fingerprints in every run file; frozen shuffle seed | the first question a reviewer will ask |

The strongest result the protocol can produce is a hazard proposed by a model, missed by the panel,
judged valid by blind adjudicators, and **later observed in operation**.

## Status

A pilot on 3 real files (35 panel hazards, 3 models, 90 runs) was completed in November 2026; see
[Pilot results](#pilot-results) and the [pilot note](docs/PILOT.md). Blind peer adjudication of the
model-only hazards is the next step, followed by the full campaign.

The real files are operational safety data and are **not** in this repository, nor are any
outputs from them; only aggregate figures are reported. Everything here runs on a fictional example
(files `FIC-01`, `FIC-02`, invented for this repository) and on a mock provider, so the whole
pipeline runs offline, without API keys, and in CI.

## Pilot results

Blind condition, share of the 35 panel hazards found, counting full and partial matches
(the partial rule is explained below), pooled over the three files:

| Model | Hazards proposed per run | Recall, one run | Recall, five runs |
|---|---|---|---|
| Claude Sonnet 4.6 | 22 | 18 % | 66 % |
| GPT-5.1 | 31 | 18 % | 43 % |
| Gemini 3.1 Pro (preview) | 7 | 7 % | 29 % |

What the pilot showed:

1. **Matching, not generation, is the measurement bottleneck.** Word-level matching found almost
   none of the panel's hazards; embedding similarity barely tracked the reviewer's judgement
   (AUC 0.63, no threshold above 13 % precision). Deciding whether a model found a hazard needs an
   expert, so matching is now manual, assisted by ranking.
2. **One consultation understates a model's contribution.** Five runs found three to four times more
   panel hazards than one.
3. **Granularity drives the result.** Counting full matches only, recall stays at or below 10 % per
   run. Most matches are partial, largely because models state one notion per hazard while reports
   often group several (e.g. "wind, QNH and QFE data erroneous" against "wind data erroneous" and
   "QNH/QFE measurement erroneous"). The review codes now separate this *component* case from other
   partial *overlap*.
4. **Volume differs fourfold between models** (7 to 31 hazards per run), so recall cannot be read
   without the validity of what is proposed.
5. **Preliminary, unblinded observation:** the study lead and a second reader judged every model-only
   hazard they read relevant, some more relevant than hazards the panels retained. Both knew the
   files and the origin of the hazards; this is the hypothesis that blind peer adjudication must test.

Pilot limits: 3 files and 35 hazards (no difference between models is established), one reviewer
with the partial rule written after the review, top-10 review depth (a lower bound), verbatim rather
than normalised panel hazards, temperature 1.0, a preview Gemini version. Run-to-run stability and
inter-model agreement, computed with word-level matching, came out near zero and are treated as a
measurement artefact until checked by hand.

## Indicators

| Indicator | Meaning |
|---|---|
| `recall_per_run` | share of the panel's hazards a single consultation finds |
| `recall_union` | share found by any of the runs; grows with repetitions, so it is reported next to the per-run value |
| `novel_union` | model hazards with no panel match: candidates for adjudication, not findings |
| `count_sd` | spread of the number of hazards per run |
| `content_stability` | mean Jaccard between runs of one model: do repeated runs propose the *same* hazards? |
| `jaccard_per_run` | agreement between two models, consultation by consultation |
| `jaccard_union` | agreement on the union of runs; drifts towards 1 with repetitions |

The [walkthrough notebook](notebooks/protocol_walkthrough.ipynb) shows each of them on the example.
Its numbers describe the mock, not any real model.

[`notebooks/pilot_colab.ipynb`](notebooks/pilot_colab.ipynb) runs the 3-file pilot (90 calls) in Google
Colab on your own anonymised canvas, with keys from the Colab secrets manager: campaign, assisted manual
matching (review workbooks to fill in), recall under strict, component and broad rules, all models
combined, and a sampled blind adjudication workbook for peers.

`content_stability` and the `jaccard_*` indicators rely on word-level matching; on real files they came
out near zero in the pilot and should be checked on a hand-judged sample before being reported.

## Usage

```bash
git clone https://github.com/MoustaphaRouf/llm-hazard-id-eval
cd llm-hazard-id-eval
pip install -e ".[providers,dev]"
pytest -q
```

```python
from hazid import adjudication, canvas, contamination, generation, matching
from hazid.protocol import Protocol

dossiers = canvas.load_canvas("canevas-synthese-eds.xlsx")       # anonymised canvas
assert not contamination.check(dossiers)

protocol = Protocol()                                            # edit, then freeze
generation.check_models(protocol, list(protocol.models))        # exact versions exist?
print(protocol.warnings(), protocol.fingerprint())               # write both to the study log

generation.run_campaign(dossiers, protocol, "runs/")             # resumable
runs = generation.load_runs("runs/")
humans = {k: d.human_labels for k, d in dossiers.items()}
matching.calibration_table(runs, humans, calibration_dossiers=["EDS-01", "EDS-02"])
protocol.match_threshold = 0.55                                  # by manual review, then frozen
evaluation = [r for r in runs if r["dossier"] not in {"EDS-01", "EDS-02"}]
matching.metrics(evaluation, humans, protocol.match_threshold)

adjudication.write_workbook(evaluation, {k: d.human_hazards for k, d in dossiers.items()},
                            "adjudication-aveugle.xlsx", protocol.shuffle_seed)
adjudication.export_for_adjudicators("adjudication-aveugle.xlsx", "adjudication-a-transmettre.xlsx")
```

API keys are read from `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `GOOGLE_API_KEY` only; in Colab,
use the secrets manager. The canvas format is described in [`src/hazid/canvas.py`](src/hazid/canvas.py).

## Confidentiality

- Use only an anonymised canvas: file identifiers, no centre or participant names.
- Obtain written authorisation before sending file contents to external APIs.
- **Never share an executed notebook or run files**: they contain the files' content. The
  `.gitignore` excludes `runs/`, `data/` and spreadsheets for that reason.

## Changes from the original Colab notebook

The code was refactored from the study notebook and its two scripts (generation and matching, V2).

- **Calibration restricted to named calibration files.** The protocol fixes the threshold on two
  test files before results are examined; the original calibration cell scanned thresholds on all
  files, letting results inform the threshold.
- **Moving model aliases flagged.** One configuration used `gemini-pro-latest`, an alias that
  changes version silently and breaks comparability between campaign days. `Protocol.warnings()`
  now reports any `latest` / `preview` / `-exp` identifier.
- **Per-run indicators added** (`recall_per_run`, `content_stability`, `jaccard_per_run`): the
  original reported only union-of-runs values, which rise mechanically with repetitions, and
  measured stability on the *number* of hazards only.
- **Optional near-duplicate merging before adjudication** (`collapse_threshold`). Exact
  de-duplication alone can leave several hundred paraphrases per file for the adjudicators;
  merged lines keep, in the key, how many models converged on them.
- **Protocol fingerprint** in every run file; failed runs archived with their error.
- **Offline mock provider and tests**, run by GitHub Actions.

## Limitations

- Automatic matching, lexical or semantic, does not reproduce an expert's judgement of "same
  hazard" (pilot: AUC 0.63); recall therefore rests on manual review, with its own reliability to
  establish (second coder, Cohen's kappa) and a review depth that makes it a lower bound.
- Results depend on how the reference is worded: composite panel hazards turn many model hits into
  partial matches. Normalising the panel hazards (one notion per entry, by a person) reduces this.
- The panel's list is a reference, not ground truth: a model hazard absent from it may be a
  genuine miss or noise. Only blind adjudication, and later operational evidence, can tell.
- Retrospective: the model does not interact with the panel, so the effect of its suggestions on
  a live discussion (anchoring, deference) is not measured.

## Prompts (English translation, for reference; the French text is the protocol)

**System.** You take part in a hazard identification session (FHA) for a safety assessment of a
change in air traffic management. You act as an air navigation safety expert, reasoning only from
the information provided. A hazard is a condition or state that may contribute to an unsafe event,
distinct from its cause and its consequence. One hazard per entry, phrased "event leading to
consequence"; cover nominal, degraded and transition conditions and the technical, procedural,
human and organisational dimensions; propose no mitigation yet. Answer with a JSON object only.

**Blind.** Identify all hazards associated with the change described below. Be exhaustive.

**Challenger.** A panel of experts has already identified the hazards listed at the end. Do not
rephrase that list: complete it, with attention to uncovered operating conditions, degraded modes,
combined failures and the human and organisational dimensions.

## Résumé en français

Protocole rétrospectif pour évaluer la participation d'un modèle de langage à la séance
d'identification des dangers (FHA/PSSA) d'une étude de sécurité ATM : deux conditions (aveugle,
challenger), trois modèles, cinq répétitions, contrôle anti-contamination, appariement manuel
assisté (codes *même danger / composante / recouvrement / différent*), adjudication en aveugle par
des pairs. Un pilote sur 3 dossiers (35 dangers, 90 exécutions) montre que les modèles couvrent,
critère large, de 29 à 66 % des dangers du panel en cinq exécutions, mais au plus 18 % en une seule,
et que l'appariement automatique ne remplace pas le jugement d'expert. Les dossiers réels ne sont
pas publiés ; seuls des chiffres agrégés le sont, et le code s'exécute sur un exemple fictif.

## License

MIT — Moustapha Amadou Roufaï
