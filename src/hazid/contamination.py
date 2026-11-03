"""Anti-contamination check.

In the blind condition the model must not be able to read the answer: no
human hazard should already appear in the pre-session context. A hazard is
flagged when 85 % or more of its significant words occur in the context.
This complements, and does not replace, the manual check recorded in the
canvas.
"""
from __future__ import annotations

from .canvas import Dossier
from .matching import normalise

GENERIC_STOPWORDS = {
    "de", "la", "le", "les", "des", "du", "un", "une", "et", "a", "au", "aux", "en", "par", "pour",
    "dans", "sur", "avec", "entre", "ou", "non", "est", "sont", "conduisant", "vers", "lors",
}
# ATC terms present in both sheets without real contamination; extend if false positives appear.
DOMAIN_STOPWORDS = {
    "surveillance", "secteur", "source", "sources", "controle", "controleur", "controleurs",
    "position", "positions", "systeme", "systemes", "trafic", "aerien", "service", "services",
    "procedure", "procedures", "donnees", "information", "informations", "mode", "modes",
    "situation", "changement",
}


def check(dossiers: dict[str, Dossier], threshold: float = 0.85,
          stopwords: set[str] = GENERIC_STOPWORDS | DOMAIN_STOPWORDS) -> list[dict]:
    alerts = []
    for did, d in sorted(dossiers.items()):
        context_words = set(normalise(d.context).split())
        for h in d.human_labels:
            sig = [w for w in normalise(h).split() if w not in stopwords and len(w) > 3]
            if not sig:
                continue
            cover = sum(w in context_words for w in sig) / len(sig)
            if cover >= threshold:
                alerts.append({"dossier": did, "overlap": round(cover, 2), "hazard": h[:90]})
    return alerts
