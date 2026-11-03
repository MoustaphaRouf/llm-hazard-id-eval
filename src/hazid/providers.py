"""Model providers. API keys are read from environment variables only:
ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY. Never put a key in code or
in a notebook cell; in Colab, use the secrets manager.
"""
from __future__ import annotations

import hashlib
import json
import os
import random


class Provider:
    name = "base"
    _cached = None

    def _client(self):
        if self._cached is None:
            self._cached = self._make_client()
        return self._cached

    def _make_client(self):
        raise NotImplementedError

    def complete(self, model: str, system: str, prompt: str, temperature: float, max_tokens: int) -> str:
        raise NotImplementedError

    def check_model(self, model: str) -> None:
        """Raise if the model identifier does not exist for this provider."""


class AnthropicProvider(Provider):
    name = "anthropic"

    def _make_client(self):
        import anthropic
        return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def complete(self, model, system, prompt, temperature, max_tokens):
        # Current Anthropic API/SDK versions no longer accept temperature, top_p or top_k:
        # sampling always uses the default temperature of 1.0, and nothing replaces it.
        # https://platform.claude.com/docs/en/api/migration-2026-10-21
        if temperature != 1.0:
            raise ValueError(f"Anthropic models sample at temperature 1.0 only (got {temperature}); "
                             "set Protocol.temperature = 1.0 so that all models share the same setting")
        r = self._client().messages.create(model=model, max_tokens=max_tokens,
                                           system=system, messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in r.content if b.type == "text")

    def check_model(self, model):
        self._client().models.retrieve(model)


class OpenAIProvider(Provider):
    name = "openai"

    def _make_client(self):
        from openai import OpenAI
        return OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def complete(self, model, system, prompt, temperature, max_tokens):
        r = self._client().chat.completions.create(
            model=model, temperature=temperature, max_completion_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}])
        return r.choices[0].message.content

    def check_model(self, model):
        self._client().models.retrieve(model)


class GoogleProvider(Provider):
    name = "google"

    def _make_client(self):
        from google import genai
        return genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    def complete(self, model, system, prompt, temperature, max_tokens):
        from google.genai import types
        r = self._client().models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system, temperature=temperature,
                                               max_output_tokens=max_tokens,
                                               response_mime_type="application/json"))
        return r.text

    def check_model(self, model):
        self._client().models.get(model=model)


PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider, "google": GoogleProvider}


class MockProvider(Provider):
    """Deterministic stand-in for offline runs, demos and tests.

    For each dossier context it draws hazards from a pool of candidate
    formulations; each model has its own inclusion rate, and the draw changes
    from run to run (seeded by model, prompt and call number), so stability
    and inter-model agreement are non-trivial. In the challenger condition it
    only proposes pool items that are not in the human list given in the prompt.
    """

    name = "mock"

    def __init__(self, pools: dict[str, list[str]], inclusion: dict[str, float] | None = None, seed: int = 0):
        self.pools = pools                       # dossier context -> candidate hazards
        self.inclusion = inclusion or {}
        self.seed = seed
        self._calls: dict[str, int] = {}

    def complete(self, model, system, prompt, temperature, max_tokens):
        context = next((c for c in self.pools if c in prompt), None)
        if context is None:
            return json.dumps({"dangers": []})
        key = f"{model}|{prompt}"
        n = self._calls[key] = self._calls.get(key, 0) + 1
        rng = random.Random(int(hashlib.sha256(f"{self.seed}|{key}|{n}".encode()).hexdigest(), 16))
        pool = self.pools[context]
        if "DANGERS DÉJÀ IDENTIFIÉS" in prompt:
            given = prompt.split("DANGERS DÉJÀ IDENTIFIÉS PAR LE PANEL", 1)[1]
            pool = [h for h in pool if h not in given]
        p = self.inclusion.get(model, 0.6)
        picked = [h for h in pool if rng.random() < p]
        hazards = [{"reference": f"IA-{i:02d}", "libelle": h, "condition_operationnelle": "nominale"}
                   for i, h in enumerate(picked, 1)]
        return json.dumps({"dangers": hazards}, ensure_ascii=False)
