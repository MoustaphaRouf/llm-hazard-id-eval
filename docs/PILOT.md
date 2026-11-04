# Pilot note: LLMs in ATM hazard identification

*November 2026 — Moustapha Amadou Roufaï*

Placed after the fact in a hazard-identification panel's position, three frontier language models
covered up to two thirds of the panel's hazards over five runs, but a single consultation covered
at most 18 %, and judging whether a model hazard "is the same" as a panel hazard could not be
automated. This note reports a feasibility pilot on three completed air traffic management (ATM)
safety assessments; it supports no ranking of models. Only aggregate figures are given: the files
are operational safety data.

## Setup

- **Files**: 3 anonymised safety assessments of ATM changes, 35 hazards identified by the human
  panels (8 to 18 per file). Files whose reference contained hazards transcribed with AI help were
  excluded.
- **Conditions**: *blind*, where the model receives only the pre-session context and must identify
  the hazards; *challenger*, where it also receives the panel's list and must find what is missing.
- **Models**: Claude Sonnet 4.6, GPT-5.1, Gemini 3.1 Pro (preview); 5 runs per file and condition,
  temperature 1.0 for all (the only value the current Anthropic API accepts). 90 runs, all valid.
- **Matching**: model hazards were compared with the panel's verbatim wording. For each panel
  hazard, a local embedding model ranked all model formulations, and one reviewer judged the top 10
  without knowing which model produced them: *same hazard*, *partial*, or *different*.
- **Partial rule**, written after the review: a model hazard that isolates one component of a
  composite panel hazard counts as found. Models are instructed to state one notion per hazard;
  reports often group several ("wind, QNH and QFE data erroneous" against "wind data erroneous" and
  "QNH/QFE measurement erroneous").

## Results (blind condition)

Share of the 35 panel hazards found, counting *same* and *partial*, pooled over the three files.

| Model | Hazards proposed per run | Recall, one run | Recall, five runs |
|---|---|---|---|
| Claude Sonnet 4.6 | 22 | 18 % | 66 % (23/35) |
| GPT-5.1 | 31 | 18 % | 43 % (15/35) |
| Gemini 3.1 Pro | 7 | 7 % | 29 % (10/35) |

Counting *same* only, recall stays at or below 10 % per run and 25 % over five runs, for every
model and file. 19 of the 34 panel hazards found by any model or condition are reached only through
*partial* matches. In the challenger condition recall is low by design, since models were told not
to repeat the panel's list; its value lies in new hazards, which have yet to be adjudicated.

## What the pilot shows

1. **The protocol runs end to end on real files.** Anonymisation, anti-contamination check, three
   providers, resumable campaign and blind adjudication workbook all worked; GPT-5.1 cost under
   USD 1 for its 30 runs.
2. **Matching, not generation, is the measurement bottleneck.** Word-level matching found almost
   none of the panel's hazards. Semantic similarity barely separated the reviewer's *same* from
   *different* (AUC 0.63), and no threshold gave more than 13 % precision. Deciding whether a model
   has found a given hazard needs a domain expert.
3. **One consultation understates what a model can contribute.** Five runs found three to four
   times more panel hazards than one: each run explores a different part of the change.
4. **Granularity drives the result.** Most matches are partial because models split the reports'
   composite hazards. Whether a model "finds" a hazard depends as much on how the reference is
   worded as on the model.
5. **Volume differs fourfold between models** (7 to 31 hazards per run), so recall cannot be read
   without the validity of what is proposed.

**Preliminary observation, not blinded.** Reading the hazards proposed by the models and absent from
the panels' lists, the study lead judged all of them relevant, and some more relevant than hazards
the panels had retained; a second reader, an intern working on the study, confirmed this reading.
This is the most promising signal of the pilot, and the one most exposed to bias: both readers know
the files, worked together, and knew which hazards came from models. It is a hypothesis for blind
adjudication, not a result.

## Limitations

- Three files and 35 hazards: per-run standard deviations are as large as the means, so no
  difference between models is established.
- One reviewer, and the *partial* rule was written after the review; *partial* also covers overlaps
  other than decomposition (composite panel hazards drew only slightly more partial matches than
  simple ones, 3.1 against 2.6).
- Only the top 10 candidates per panel hazard were reviewed, and matches still appeared at ranks 9
  and 10: recall is a lower bound.
- Panel hazards were used verbatim, not in the normalised one-notion form the protocol specifies.
- Temperature 1.0 throughout; Gemini was a preview version, which may change without notice.
- Run-to-run stability and inter-model agreement were computed with word-level matching and are not
  reported here.

## Next steps

Implemented in the repository after the pilot: review codes *component* and *overlap* in place of
*partial*, review depth of 20, recall for all models combined, sampled adjudication workbook.

1. Have a second reviewer recode one file against the written rule and report Cohen's kappa.
2. Normalise the panel hazards (one notion per entry) before the full campaign, by a person rather
   than a model.
3. Have peers who do not know the files adjudicate a sample of model-only hazards blind, which
   tests the observation above.
4. Extend to the remaining files, then confront model-only hazards judged valid with occurrences
   reported after the changes went live.
