"""Phase 1: submit every file to every model, in each condition, with repetitions.

Each run is archived as one JSON file named
``<dossier>__<model key>__<condition>__run<NN>.json``. The campaign is
resumable: a run whose file already exists is skipped, so an interrupted
campaign is simply relaunched.
"""
from __future__ import annotations

import datetime
import json
import time
from pathlib import Path

from .canvas import Dossier
from .protocol import SYSTEM_PROMPT, Protocol, build_prompt, prompt_fingerprint
from .providers import PROVIDERS, Provider


def extract_json(raw: str) -> dict:
    """Isolate the JSON object even if the model wrapped it in text or code fences."""
    t = raw.strip()
    if t.startswith("```"):
        t = t.split("```")[1]
        t = t[4:] if t.lower().startswith("json") else t
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in the response")
    return json.loads(t[start:end + 1])


def check_models(protocol: Protocol, keys: list[str], providers: dict[str, Provider] | None = None) -> bool:
    """Verify model identifiers with each provider before freezing the protocol."""
    ok = True
    for key in keys:
        cfg = protocol.models[key]
        prov = (providers or {}).get(cfg["provider"]) or PROVIDERS[cfg["provider"]]()
        try:
            prov.check_model(cfg["model"])
            print(f"  ok  {key} ({cfg['model']})")
        except Exception as e:  # noqa: BLE001 - report every provider error
            print(f"  NOT FOUND  {key} ({cfg['model']}): {e}")
            ok = False
    for w in protocol.warnings():
        print("  warning:", w)
    return ok


def run_campaign(dossiers: dict[str, Dossier], protocol: Protocol, out_dir: str | Path,
                 conditions=("blind", "challenger"), keys: list[str] | None = None,
                 providers: dict[str, Provider] | None = None, pause_s: float = 2.0) -> dict:
    """Run (dossier x condition x model x repetition); return counts.

    The challenger condition is only run for files that have a human hazard
    list. ``providers`` overrides the real API clients (e.g. with a
    :class:`~hazid.providers.MockProvider`).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    keys = keys or list(protocol.models)
    clients = {name: (providers or {}).get(name) or cls() for name, cls in PROVIDERS.items()}
    clients.update(providers or {})
    counts = {"run": 0, "failed": 0, "skipped": 0}

    for did, d in sorted(dossiers.items()):
        for cond in conditions:
            if cond == "challenger" and not d.human_hazards:
                continue
            prompt = build_prompt(cond, d.context, d.human_labels)
            fp = prompt_fingerprint(SYSTEM_PROMPT, prompt)
            for key in keys:
                cfg = protocol.models[key]
                for n in range(1, protocol.n_runs + 1):
                    path = out / f"{did}__{key}__{cond}__run{n:02d}.json"
                    if path.exists():
                        counts["skipped"] += 1
                        continue
                    counts["run"] += 1
                    try:
                        raw = clients[cfg["provider"]].complete(
                            cfg["model"], SYSTEM_PROMPT, prompt, protocol.temperature, protocol.max_tokens)
                        hazards, status, error = extract_json(raw).get("dangers", []), "ok", None
                    except Exception as e:  # noqa: BLE001 - archived as a failed run
                        raw, hazards, status, error = "", [], "failed", str(e)
                        counts["failed"] += 1
                    path.write_text(json.dumps({
                        "dossier": did, "model_key": key, "provider": cfg["provider"], "model": cfg["model"],
                        "condition": cond, "run": n, "temperature": protocol.temperature,
                        "prompt_fingerprint": fp, "protocol_fingerprint": protocol.fingerprint(),
                        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
                        "status": status, "error": error, "n_hazards": len(hazards),
                        "hazards": hazards, "raw_response": raw,
                    }, ensure_ascii=False, indent=2), encoding="utf-8")
                    if pause_s:
                        time.sleep(pause_s)
    return counts


def load_runs(out_dir: str | Path, ok_only: bool = True) -> list[dict]:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(out_dir).glob("*.json"))]
    return [r for r in runs if r["status"] == "ok"] if ok_only else runs
