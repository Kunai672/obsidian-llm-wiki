"""
LLM client interface and implementations.
"""
from __future__ import annotations

import json
import os
import urllib.request
from abc import ABC, abstractmethod
from typing import Any


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def complete(self, system: str, prompt: str) -> str:
        """Send a completion request and return the response text."""
        pass


class OpenAICompatibleClient(LLMClient):
    """Client for OpenAI-compatible APIs (llama.cpp, NVIDIA NIM, etc.)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.base_url = base_url or os.environ.get("LLMWIKI_BASE_URL")
        self.api_key = api_key or os.environ.get("LLMWIKI_API_KEY")
        self.model = model or os.environ.get("LLMWIKI_MODEL")

        if not self.base_url:
            raise ValueError("LLMWIKI_BASE_URL not set")
        if not self.model:
            raise ValueError("LLMWIKI_MODEL not set")

        # Ensure base_url ends with /v1
        if not self.base_url.rstrip("/").endswith("/v1"):
            self.base_url = self.base_url.rstrip("/") + "/v1"

    def complete(self, system: str, prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        return result["choices"][0]["message"]["content"]


class FakeLLMClient(LLMClient):
    """Fake LLM client for testing with deterministic canned responses."""

    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.call_log: list[tuple[str, str]] = []

    def complete(self, system: str, prompt: str) -> str:
        self.call_log.append((system, prompt))
        # Match by checking if any key is in the prompt
        for key, response in self.responses.items():
            if key in prompt:
                return response
        # Default response
        return '{"edits": [], "log_note": "No matching canned response"}'

    def set_response(self, key: str, response: str) -> None:
        """Set a canned response for a prompt containing key."""
        self.responses[key] = response

    @classmethod
    def demo(cls) -> "FakeLLMClient":
        """Create a FakeLLMClient with demo responses for CLI usage.
        
        These responses handle the common prompts from:
        - ingest: edit proposal prompt
        - query step 1: page selection prompt
        - query step 2: answer prompt
        - lint deep: contradiction check prompt
        """
        import yaml
        
        def make_page(title: str, ptype: str, summary: str, sources: list[str], tags: list[str], updated: str, body: str) -> str:
            fm = {"title": title, "type": ptype, "summary": summary, "sources": sources, "tags": tags, "updated": updated}
            yaml_str = yaml.dump(fm, sort_keys=False).strip()
            return f"---\n{yaml_str}\n---\n\n{body}"

        # Demo responses keyed by stable prompt markers
        demo_responses = {
            # Ingest: "select up to" is in the ingest prompt
            "Raw source:": json.dumps({
                "edits": [
                    {
                        "path": "sources/demo-source.md",
                        "action": "create",
                        "content": make_page(
                            "Demo Source", "source", "Demo source summary",
                            ["raw/demo.md"], ["demo"], "2025-01-15",
                            "This demo source mentions [[demo-entity]] and [[demo-concept]]."
                        )
                    },
                    {
                        "path": "entities/demo-entity.md",
                        "action": "create",
                        "content": make_page(
                            "Demo Entity", "entity", "A demo entity",
                            ["raw/demo.md"], ["demo", "entity"], "2025-01-15",
                            "Demo entity is related to [[demo-concept]]."
                        )
                    },
                    {
                        "path": "concepts/demo-concept.md",
                        "action": "create",
                        "content": make_page(
                            "Demo Concept", "concept", "A demo concept",
                            ["raw/demo.md"], ["demo", "concept"], "2025-01-15",
                            "Demo concept relates to [[demo-entity]]."
                        )
                    }
                ],
                "log_note": "Created demo source, entity, and concept pages"
            }),
            # Query step 1: "select up to" is in the page selection prompt
            "select up to": '["overview", "demo-entity", "demo-concept"]',
            # Query step 2: "Answer the question using ONLY" is in the answer prompt
            "Answer the question using ONLY": "Based on the wiki, the demo entity [[demo-entity]] is a demo entity related to [[demo-concept]]. See also the [[overview]] page.",
            # Lint deep: "Compare these two wiki pages" is in the deep lint prompt
            "Compare these two wiki pages": "[]",
        }
        return cls(demo_responses)


def get_llm_client() -> LLMClient:
    """Get the appropriate LLM client based on environment."""
    backend = os.environ.get("LLMWIKI_BACKEND", "openai")
    if backend == "fake":
        return FakeLLMClient.demo()
    return OpenAICompatibleClient()