"""The model boundary: one method, `complete(system, user) -> str`.

ChatLLM talks to any OpenAI-compatible endpoint (Gemini's compatibility endpoint by default,
or OpenRouter). ScriptedLLM replays canned replies so the whole loop is testable offline.
"""
import os
import time
from typing import Protocol

from openai import APIConnectionError, InternalServerError, OpenAI, RateLimitError

PROVIDERS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
    "openrouter": ("https://openrouter.ai/api/v1", ("OPENROUTER_API_KEY",)),
}
DEFAULT_MODELS = {"gemini": "gemini-3.8-flash", "openrouter": "openrouter/free"}


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class ChatLLM:
    def __init__(self, base_url: str, api_key: str, model: str, temperature: float = 0.7,
                 max_retries: int = 6):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model.removeprefix("models/")  # Gemini lists ids as "models/<id>"
        self.temperature = temperature
        self.max_retries = max_retries

    def complete(self, system: str, user: str) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for attempt in range(self.max_retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model, messages=messages, temperature=self.temperature)
                return resp.choices[0].message.content or ""
            except (RateLimitError, InternalServerError, APIConnectionError) as e:
                wait = min(2 ** attempt * 3, 60)
                print(f"  [llm retry {attempt + 1}/{self.max_retries} in {wait}s: {type(e).__name__}]")
                time.sleep(wait)
        raise RuntimeError("model unavailable after retries")

    def list_models(self) -> list[str]:
        return sorted(m.id.removeprefix("models/") for m in self.client.models.list())


def from_env(model: str | None = None) -> ChatLLM:
    provider = os.environ.get("AUTORESEARCH_PROVIDER", "gemini").lower()
    if provider not in PROVIDERS:
        raise SystemExit(f"AUTORESEARCH_PROVIDER must be one of {sorted(PROVIDERS)}, got {provider!r}")
    base_url, key_vars = PROVIDERS[provider]
    key = next((os.environ[v].strip() for v in key_vars if os.environ.get(v, "").strip()), "")
    if not key:
        raise SystemExit(f"Set one of {', '.join(key_vars)} in this terminal first (provider: {provider}).")
    model = model or os.environ.get("AUTORESEARCH_MODEL") or DEFAULT_MODELS[provider]
    return ChatLLM(base_url, key, model)


class ScriptedLLM:
    """Returns canned replies in order; used by tests and offline demos."""

    def __init__(self, replies: list[str]):
        self.replies = list(replies)
        self.prompts: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        if not self.replies:
            raise RuntimeError("ScriptedLLM has no replies left")
        return self.replies.pop(0)
