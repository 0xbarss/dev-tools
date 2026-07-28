"""Pluggable AI backend abstraction (proposal deep-dive #5).

Every AI-flavored command (`explain`, `review`, `changelog --ai-summary`)
goes through this one module so they share a single, swappable client
configured via `devtools config set ai_provider <claude|openai|ollama>`.

Design notes:
  - A small `Protocol`-style interface: `complete(prompt, system=None) -> str`.
  - One thin adapter per provider, mirroring `deps_engine.py`'s
    one-engine-per-ecosystem pattern.
  - No provider SDKs required: adapters talk HTTP directly via the stdlib
    `urllib`, so `llm_client.py` adds zero new hard dependencies.
  - Cloud providers (Claude, OpenAI) are gated behind `allow_network`,
    matching the project's existing network-is-opt-in philosophy. Ollama
    is treated as local (no outbound network) and is not gated.
  - API keys are always read from the provider's standard environment
    variable and are never written to config.toml.
"""

from __future__ import annotations

import json as _json
import os
import urllib.error
import urllib.request
from typing import Optional, Protocol

from devtools.models.settings import Settings

_DEFAULT_MODELS = {
    "claude": "claude-sonnet-4-6",
    "openai": "gpt-4.1-mini",
    "ollama": "llama3.1",
}

_TIMEOUT_SECONDS = 60


class LLMClientError(RuntimeError):
    """Raised for any AI-backend configuration or request failure."""


class LLMClient(Protocol):
    provider: str

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        ...


class NoneClient:
    """The default, no-op provider. Every AI command should check for this
    and fail with a clear, actionable message rather than calling complete()."""

    provider = "none"

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        raise LLMClientError(
            "No AI provider configured. Run `devtools config set ai_provider "
            "claude|openai|ollama` (and set the matching API key env var, or "
            "start Ollama locally) to enable AI-assisted commands."
        )


class ClaudeClient:
    provider = "claude"
    _url = "https://api.anthropic.com/v1/messages"

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        body: dict = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        headers = {
            "content-type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
        }
        data = _post_json(self._url, body, headers)
        try:
            blocks = data["content"]
            return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        except (KeyError, TypeError) as exc:
            raise LLMClientError(f"Unexpected Claude API response shape: {data!r}") from exc


class OpenAIClient:
    provider = "openai"
    _url = "https://api.openai.com/v1/chat/completions"

    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._api_key = api_key

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {"model": self.model, "messages": messages}
        headers = {"content-type": "application/json", "authorization": f"Bearer {self._api_key}"}
        data = _post_json(self._url, body, headers)
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError(f"Unexpected OpenAI API response shape: {data!r}") from exc


class OllamaClient:
    provider = "ollama"

    def __init__(self, model: str, host: str = "http://localhost:11434") -> None:
        self.model = model
        self._url = host.rstrip("/") + "/api/generate"

    def complete(self, prompt: str, system: Optional[str] = None) -> str:
        body = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            body["system"] = system
        try:
            data = _post_json(self._url, body, {"content-type": "application/json"})
        except LLMClientError as exc:
            raise LLMClientError(
                f"Could not reach Ollama at {self._url} ({exc}). Is `ollama serve` running?"
            ) from exc
        try:
            return data["response"].strip()
        except (KeyError, TypeError) as exc:
            raise LLMClientError(f"Unexpected Ollama API response shape: {data!r}") from exc


def _post_json(url: str, body: dict, headers: dict) -> dict:
    payload = _json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMClientError(f"{url} returned HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise LLMClientError(f"Could not reach {url}: {exc.reason}") from exc
    try:
        return _json.loads(raw)
    except _json.JSONDecodeError as exc:
        raise LLMClientError(f"{url} returned non-JSON response") from exc


def get_client(settings: Settings) -> LLMClient:
    """Build the configured LLM client (spec: `ai.provider` / `ai_provider`).

    Raises `LLMClientError` with an actionable message if the provider is
    unset, unknown, or missing required configuration (API key / network
    permission) rather than silently falling back to a different provider.
    """
    provider = (settings.ai_provider or "none").strip().lower()
    model = settings.ai_model

    if provider in ("none", ""):
        return NoneClient()

    if provider == "claude":
        if not settings.allow_network:
            raise LLMClientError(
                "ai_provider is 'claude' but allow_network is false. Run "
                "`devtools config set allow_network true` to permit calling the Claude API."
            )
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMClientError("ANTHROPIC_API_KEY is not set in the environment.")
        return ClaudeClient(model or _DEFAULT_MODELS["claude"], api_key)

    if provider == "openai":
        if not settings.allow_network:
            raise LLMClientError(
                "ai_provider is 'openai' but allow_network is false. Run "
                "`devtools config set allow_network true` to permit calling the OpenAI API."
            )
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise LLMClientError("OPENAI_API_KEY is not set in the environment.")
        return OpenAIClient(model or _DEFAULT_MODELS["openai"], api_key)

    if provider == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        return OllamaClient(model or _DEFAULT_MODELS["ollama"], host=host)

    raise LLMClientError(
        f"Unknown ai_provider {provider!r}. Supported: none, claude, openai, ollama."
    )
