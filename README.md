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
| Repetitions | 5 runs at temperature 0.7 | a hazard that appears once in five runs is not the same evidence as one that appears every time |
| Anti-contamination | automatic lexical check + manual check | no panel hazard may leak into the blind context |
| Matching | TF-IDF similarity, threshold fixed on calibration files before results | *proposes* correspondences only |
| Judgement | blind adjudication by peers who do not know the files: panel and model hazards mixed, origin hidden | no model grades its own output, and the study lead does not adjudicate |
| Reproducibility | prompt and protocol fingerprints in every run file; frozen shuffle seed | the first question a reviewer will ask |

The strongest result the protocol can produce is a hazard proposed by a model, missed by the panel,
judged valid by blind adjudicators, and **later observed in operation**.

## Status

The protocol and the tooling are complete and tested; a pilot on real files has started. The real
files are operational safety data and are **not** in this repository, nor are any outputs from
them. Everything here runs on a fictional example (files `FIC-01`, `FIC-02`, invented for this
repository) and on a mock provider, so the whole pipeline runs offline, without API keys, and in CI.

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
- **Offline mock provider and 11 tests**, run by GitHub Actions.

## Limitations

- Lexical matching misses paraphrases with different vocabulary and can pair distinct hazards that
  share words; it only pre-selects, and the threshold must be checked by hand.
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
challenger), trois modèles, cinq répétitions, contrôle anti-contamination, appariement lexical
calibré avant résultats, adjudication en aveugle par des pairs. Les dossiers réels ne sont pas
publiés ; tout s'exécute sur un exemple fictif et un fournisseur simulé.

## License

MIT — Moustapha Amadou Roufaï
