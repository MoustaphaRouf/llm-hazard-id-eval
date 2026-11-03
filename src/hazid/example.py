"""A fully fictional example for demos and tests.

Nothing here comes from a real safety assessment: the aerodrome, the changes,
the panel's hazards and the "model" outputs were invented for this repository
to exercise the pipeline. Identifiers use the FIC- prefix to make that obvious.
"""
from __future__ import annotations

from .canvas import Dossier
from .providers import MockProvider

CONTEXT_FIELDS = ["Intitulé du changement", "Description", "Environnement opérationnel", "Phase de mise en œuvre"]

DOSSIERS = [
    {
        "id": "FIC-01",
        "Intitulé du changement": "Mise en service d'une procédure de départ RNAV (SID) en piste 24 à l'aérodrome fictif de Valmont",
        "Description": "Remplacement des départs conventionnels guidés au VOR par une SID RNAV 1 avec deux transitions. "
                       "Publication à l'AIRAC suivant, période de coexistence de huit semaines.",
        "Environnement opérationnel": "Approche non radar, une position de contrôle, trafic mixte commercial et aviation générale.",
        "Phase de mise en œuvre": "Formation des contrôleurs en cours, information aux exploitants prévue.",
        "hazards": [
            ("H-01", "Équipage non qualifié RNAV acceptant la SID conduisant à une déviation latérale de trajectoire"),
            ("H-02", "Confusion entre ancienne et nouvelle procédure pendant la coexistence conduisant à une clairance erronée"),
            ("H-03", "Base de données de navigation de bord non mise à jour conduisant à un suivi de trajectoire erroné"),
            ("H-04", "Perte de la couverture GNSS au départ conduisant à une dégradation de la navigation"),
            ("H-05", "Phraséologie de clairance de départ non maîtrisée conduisant à une incompréhension de l'équipage"),
        ],
    },
    {
        "id": "FIC-02",
        "Intitulé du changement": "Transfert de la position d'approche vers une salle de contrôle rénovée",
        "Description": "Déplacement des positions APP et COORD vers une nouvelle salle, nouveaux pupitres radio et téléphonie. "
                       "Bascule prévue de nuit, ancienne salle maintenue en secours un mois.",
        "Environnement opérationnel": "Approche, deux positions, trafic faible la nuit, pointes en début de matinée.",
        "Phase de mise en œuvre": "Essais techniques réalisés, procédure de bascule en rédaction.",
        "hazards": [
            ("H-01", "Interruption des communications radio pendant la bascule conduisant à une perte de contact avec les aéronefs"),
            ("H-02", "Méconnaissance des nouveaux pupitres par les contrôleurs conduisant à une erreur de sélection de fréquence"),
            ("H-03", "Retour en salle de secours non préparé conduisant à une indisponibilité prolongée du service"),
            ("H-04", "Défaillance de la téléphonie de coordination conduisant à un défaut de coordination avec le centre voisin"),
        ],
    },
]

# Candidate formulations the mock "models" draw from: close paraphrases of
# panel hazards, plausible new hazards, and a few weak entries (a cause, a
# mitigation, a duplicate) that adjudicators should reject.
POOLS = {
    "FIC-01": [
        "Équipage non qualifié RNAV acceptant la procédure SID conduisant à une déviation latérale",
        "Coexistence des deux procédures entraînant une confusion et une clairance erronée du contrôleur",
        "Base de données de navigation non mise à jour à bord conduisant à un suivi de trajectoire erroné",
        "Perte du signal GNSS au départ conduisant à une dégradation de la navigation RNAV",
        "Erreur de saisie de la transition dans le FMS conduisant à une trajectoire non conforme",
        "Divergence entre la carte publiée et le codage de la base de données conduisant à une trajectoire inattendue",
        "Charge de travail accrue du contrôleur non radar pendant la coexistence conduisant à une détection tardive d'écart",
        "Aéronef d'aviation générale non équipé demandant la SID conduisant à une gestion ad hoc non prévue",
        "Absence de moyen de surveillance pour détecter un écart de trajectoire conduisant à un conflit non détecté",
        "Former les contrôleurs à la nouvelle phraséologie",
        "Mauvaise formation",
    ],
    "FIC-02": [
        "Coupure des communications radio lors de la bascule conduisant à une perte de contact avec les aéronefs",
        "Erreur de sélection de fréquence sur les nouveaux pupitres conduisant à une communication sur une mauvaise fréquence",
        "Défaillance de la téléphonie de coordination conduisant à un défaut de coordination avec le centre voisin",
        "Bascule réalisée sans liste de vérification partagée conduisant à une configuration incomplète des positions",
        "Ergonomie de la nouvelle salle réduisant la communication entre positions APP et COORD conduisant à une perte de conscience de la situation",
        "Enregistrement des communications non opérationnel après bascule conduisant à une impossibilité d'enquête",
        "Personnel technique indisponible la nuit de bascule conduisant à un rétablissement retardé en cas de panne",
        "Prévoir une répétition générale de la bascule",
        "Coupure radio pendant la bascule",
    ],
}

MODEL_INCLUSION = {"claude-sonnet-4-6": 0.75, "gpt-5.1": 0.6, "gemini-3-pro": 0.5}


def dossiers() -> dict[str, Dossier]:
    out = {}
    for d in DOSSIERS:
        context = "\n".join(f"{f} : {d[f]}" for f in CONTEXT_FIELDS)
        out[d["id"]] = Dossier(d["id"], context, [{"reference": no, "libelle": t} for no, t in d["hazards"]])
    return out


def mock_provider(seed: int = 0) -> MockProvider:
    ds = dossiers()
    return MockProvider({ds[k].context: v for k, v in POOLS.items()}, MODEL_INCLUSION, seed)
