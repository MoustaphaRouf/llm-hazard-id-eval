"""Study protocol: prompts and frozen parameters.

The study is run in French, the working language of the safety assessments,
so the prompts are kept verbatim in French. English translations are given in
the README for reference only; the French text is the protocol.

Two experimental conditions:

* ``blind`` (``aveugle``): the model sees only the pre-session context of the
  change and must identify the hazards, as a panel member would.
* ``challenger``: the model also sees the hazards already identified by the
  human panel and must find the ones that are missing.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

SYSTEM_PROMPT = (
    "Vous participez à une séance d'identification des dangers (FHA) "
    "menée dans le cadre d'une étude de sécurité relative à une conduite du changement "
    "en gestion du trafic aérien.\n\n"
    "Votre rôle est celui d'un expert en sécurité des services de navigation aérienne. "
    "Vous raisonnez à partir des seuls éléments fournis, sans supposer d'information "
    "absente du dossier.\n\n"
    "Un danger est une condition ou un état susceptible de contribuer à un événement "
    "indésirable pour la sécurité. Il se distingue de sa cause et de sa conséquence.\n\n"
    "Règles de formulation :\n"
    "- un danger par entrée, jamais deux notions regroupées ;\n"
    "- formulation normalisée « <événement> conduisant à <conséquence> » ;\n"
    "- couvrir les conditions nominales, dégradées et de transition ;\n"
    "- inclure les dimensions technique, procédurale, humaine et organisationnelle ;\n"
    "- ne pas proposer de mesure d'atténuation à ce stade.\n\n"
    "Vous répondez EXCLUSIVEMENT par un objet JSON valide, sans texte introductif, "
    "sans commentaire et sans balises de code, conforme à ce schéma :\n\n"
    '{"dangers":[{"reference":"IA-01","libelle":"...","evenement":"...",'
    '"consequence":"...","causes":["..."],"categorie":"...",'
    '"condition_operationnelle":"nominale|degradee|transition"}]}'
)

BLIND_INSTRUCTION = (
    "Identifiez l'ensemble des dangers associés au changement "
    "décrit ci-dessous. Soyez exhaustif.\n\n"
    "DOSSIER\n{dossier}"
)

CHALLENGER_INSTRUCTION = (
    "Un panel d'experts a déjà identifié les dangers listés "
    "en fin de message pour le changement décrit ci-dessous.\n\n"
    "Votre tâche n'est PAS de reformuler cette liste, mais de la compléter : identifiez "
    "les dangers qui n'y figurent pas. Portez attention aux conditions opérationnelles "
    "non couvertes, aux modes dégradés, aux combinaisons de défaillances et aux "
    "dimensions humaine et organisationnelle.\n\n"
    "DOSSIER\n{dossier}\n\n"
    "DANGERS DÉJÀ IDENTIFIÉS PAR LE PANEL\n{liste_humaine}"
)

CONDITIONS = ("blind", "challenger")

# Aliases that silently move to newer model versions. A frozen protocol must
# name exact versions, otherwise runs made on different days are not comparable.
_MOVING_ALIASES = ("latest", "preview", "-exp")


def build_prompt(condition: str, context: str, human_hazards: list[str] | None = None) -> str:
    if condition == "blind":
        return BLIND_INSTRUCTION.format(dossier=context)
    if condition == "challenger":
        if not human_hazards:
            raise ValueError("challenger condition needs a non-empty human hazard list")
        return CHALLENGER_INSTRUCTION.format(
            dossier=context, liste_humaine="\n".join(f"- {h}" for h in human_hazards))
    raise ValueError(f"unknown condition: {condition}")


def prompt_fingerprint(system: str, prompt: str) -> str:
    return hashlib.sha256((system + prompt).encode()).hexdigest()[:16]


@dataclass
class Protocol:
    """Parameters to freeze before the first real run and record in the study log."""

    models: dict = field(default_factory=lambda: {
        "A": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
        "B": {"provider": "openai", "model": "gpt-5.1"},
        "C": {"provider": "google", "model": "gemini-3-pro"},
    })
    temperature: float = 0.7      # > 0: needed to measure run-to-run stability
    n_runs: int = 5               # repetitions per (dossier x model x condition)
    max_tokens: int = 8000
    match_threshold: float | None = None  # set from the calibration step, never after results
    shuffle_seed: int = 20260811  # order of the blind adjudication workbook

    def warnings(self) -> list[str]:
        out = []
        for key, cfg in self.models.items():
            if any(a in cfg["model"] for a in _MOVING_ALIASES):
                out.append(f"model {key} uses a moving alias ({cfg['model']}): freeze an exact version")
        if self.temperature <= 0 and self.n_runs > 1:
            out.append("temperature 0 makes repeated runs uninformative about stability")
        if self.match_threshold is None:
            out.append("match_threshold not frozen yet")
        return out

    def fingerprint(self) -> str:
        """Hash of parameters and prompts, to write in the study log."""
        payload = json.dumps({**asdict(self), "system": SYSTEM_PROMPT, "blind": BLIND_INSTRUCTION,
                              "challenger": CHALLENGER_INSTRUCTION}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]
