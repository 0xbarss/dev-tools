from __future__ import annotations

import json

import pytest

from devtools.core import llm_client
from devtools.models.settings import Settings


def test_none_provider_is_default_and_raises_on_complete():
    settings = Settings()
    client = llm_client.get_client(settings)
    assert isinstance(client, llm_client.NoneClient)
    with pytest.raises(llm_client.LLMClientError):
        client.complete("hello")


def test_claude_provider_requires_allow_network(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    settings = Settings(ai_provider="claude", allow_network=False)
    with pytest.raises(llm_client.LLMClientError, match="allow_network"):
        llm_client.get_client(settings)


def test_claude_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings = Settings(ai_provider="claude", allow_network=True)
    with pytest.raises(llm_client.LLMClientError, match="ANTHROPIC_API_KEY"):
        llm_client.get_client(settings)


def test_claude_provider_builds_client_when_configured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    settings = Settings(ai_provider="claude", allow_network=True)
    client = llm_client.get_client(settings)
    assert isinstance(client, llm_client.ClaudeClient)
    assert client.model == "claude-sonnet-4-6"


def test_openai_provider_requires_allow_network(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = Settings(ai_provider="openai", allow_network=False)
    with pytest.raises(llm_client.LLMClientError, match="allow_network"):
        llm_client.get_client(settings)


def test_ollama_provider_does_not_require_allow_network():
    settings = Settings(ai_provider="ollama", allow_network=False)
    client = llm_client.get_client(settings)
    assert isinstance(client, llm_client.OllamaClient)


def test_unknown_provider_raises():
    settings = Settings(ai_provider="not-a-real-provider")
    with pytest.raises(llm_client.LLMClientError, match="Unknown ai_provider"):
        llm_client.get_client(settings)


def test_claude_client_complete_parses_text_blocks(monkeypatch):
    captured = {}

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse({"content": [{"type": "text", "text": "hello from claude"}]})

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)
    client = llm_client.ClaudeClient(model="claude-sonnet-4-6", api_key="sk-test")
    result = client.complete("hi")
    assert result == "hello from claude"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"


def test_ollama_client_complete_reports_connection_errors(monkeypatch):
    import urllib.error

    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)
    client = llm_client.OllamaClient(model="llama3.1")
    with pytest.raises(llm_client.LLMClientError, match="ollama serve"):
        client.complete("hi")