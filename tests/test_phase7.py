"""
Phase 7 tests: search and e2e.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from llmwiki.search import search_wiki, cmd_search, _tokenize, _compute_bm25
from llmwiki.llm import FakeLLMClient
from llmwiki.wiki import init_wiki, write_page, read_page, update_index, list_pages
from llmwiki.ingest import ingest_source
from llmwiki.query import query_wiki
from llmwiki.lint import lint_wiki
import llmwiki.ingest as ingest_module
import llmwiki.query as query_module


def setup_fake_backend():
    os.environ["LLMWIKI_BACKEND"] = "fake"


def teardown_fake_backend():
    os.environ.pop("LLMWIKI_BACKEND", None)


def test_tokenize():
    """Test tokenization."""
    tokens = _tokenize("Hello, World! This is a test.")
    assert tokens == ["hello", "world", "this", "is", "a", "test"]


def test_search_ranks_title_match_higher():
    """Test that title matches rank higher than body mentions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Page with "OpenAI" in title
            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI company", "sources": [], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI is an AI research company.")

            # Page with "OpenAI" only in body
            write_page("entities/gpt-4.md", {"title": "GPT-4", "type": "entity", "summary": "Language model", "sources": [], "tags": ["ai"], "updated": "2025-01-15"}, "GPT-4 is a model from OpenAI.")

            update_index()

            results = search_wiki("OpenAI")
            assert len(results) >= 2
            # First result should be the page with OpenAI in title
            assert results[0][0] == "entities/openai.md" or "OpenAI" in results[0][1]
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_search_empty_wiki():
    """Test search on empty wiki."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            results = search_wiki("anything")
            assert results == []
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_search_cli():
    """Test search CLI command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI company", "sources": [], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI is an AI company.")
            update_index()

            result = cmd_search(["OpenAI"])
            assert result == 0
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_e2e_full_loop():
    """End-to-end test: init, ingest two fixtures, query --save, lint."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Copy fixtures to raw/
            import shutil
            fixture_dir = Path("/home/ubuntu/.treehouse/obsidian-llm-wiki-fe3be1/1/obsidian-llm-wiki/fixtures")
            raw_dir = Path("raw")
            raw_dir.mkdir(exist_ok=True)
            shutil.copy(fixture_dir / "sample1.md", raw_dir / "sample1.md")
            shutil.copy(fixture_dir / "sample2.md", raw_dir / "sample2.md")

            def make_content(title, ptype, summary, sources, tags, updated, body):
                import yaml
                fm = {"title": title, "type": ptype, "summary": summary, "sources": sources, "tags": tags, "updated": updated}
                yaml_str = yaml.dump(fm, sort_keys=False).strip()
                return f"---\n{yaml_str}\n---\n\n{body}"

            # Ingest sample1.md response
            sample1_edits = [
                {"path": "sources/sample1.md", "action": "create", "content": make_content("The Future of AI", "source", "AI in 2024 perspective", ["raw/sample1.md"], ["ai", "2024"], "2025-01-15", "Discusses [[openai]], [[anthropic]], [[meta]], [[google]], [[llama-3]], [[gemini]].")},
                {"path": "entities/openai.md", "action": "create", "content": make_content("OpenAI", "entity", "AI research company", ["raw/sample1.md"], ["ai", "company"], "2025-01-15", "OpenAI created [[gpt-4o]].")},
                {"path": "entities/anthropic.md", "action": "create", "content": make_content("Anthropic", "entity", "AI safety company", ["raw/sample1.md"], ["ai", "company"], "2025-01-15", "Anthropic created [[claude-3]].")},
                {"path": "entities/meta.md", "action": "create", "content": make_content("Meta", "entity", "Technology company", ["raw/sample1.md"], ["ai", "company"], "2025-01-15", "Meta released [[llama-3]].")},
                {"path": "entities/google.md", "action": "create", "content": make_content("Google", "entity", "Technology company", ["raw/sample1.md"], ["ai", "company"], "2025-01-15", "Google created [[gemini]].")},
                {"path": "entities/llama-3.md", "action": "create", "content": make_content("Llama 3", "entity", "Open weight model", ["raw/sample1.md"], ["ai", "model"], "2025-01-15", "Llama 3 from [[meta]].")},
                {"path": "entities/gpt-4o.md", "action": "create", "content": make_content("GPT-4o", "entity", "Multimodal model", ["raw/sample1.md"], ["ai", "model"], "2025-01-15", "GPT-4o from [[openai]].")},
                {"path": "entities/claude-3.md", "action": "create", "content": make_content("Claude 3", "entity", "Language model", ["raw/sample1.md"], ["ai", "model"], "2025-01-15", "Claude 3 from [[anthropic]].")},
                {"path": "entities/gemini.md", "action": "create", "content": make_content("Gemini", "entity", "Multimodal model", ["raw/sample1.md"], ["ai", "model"], "2025-01-15", "Gemini from [[google]].")},
            ]
            sample1_response = json.dumps({"edits": sample1_edits, "log_note": "Ingested sample1.md"})

            # Ingest sample2.md response
            sample2_edits = [
                {"path": "sources/sample2.md", "action": "create", "content": make_content("Local LLMs", "source", "Running models on consumer hardware", ["raw/sample2.md"], ["local", "llm"], "2025-01-15", "Covers [[quantization]], [[llama-cpp]], [[ollama]], [[llamafile]], [[vllm]].")},
                {"path": "concepts/quantization.md", "action": "create", "content": make_content("Quantization", "concept", "Reducing model precision", ["raw/sample2.md"], ["technique"], "2025-01-15", "Q4_K_M is the best balance.")},
                {"path": "entities/llama-cpp.md", "action": "create", "content": make_content("llama.cpp", "entity", "Inference engine", ["raw/sample2.md"], ["engine"], "2025-01-15", "Powers [[ollama]] and [[llamafile]].")},
                {"path": "entities/ollama.md", "action": "create", "content": make_content("Ollama", "entity", "Local LLM tool", ["raw/sample2.md"], ["tool"], "2025-01-15", "Wrapper around [[llama-cpp]].")},
                # Update existing entities from sample1
                {"path": "entities/meta.md", "action": "append", "content": make_content("Meta", "entity", "Technology company", ["raw/sample1.md", "raw/sample2.md"], ["ai", "company", "local"], "2025-01-15", "Meta's [[llama-3]] works well with [[llama-cpp]].")},
                {"path": "entities/llama-3.md", "action": "append", "content": make_content("Llama 3", "entity", "Open weight model", ["raw/sample1.md", "raw/sample2.md"], ["ai", "model", "local"], "2025-01-15", "Runs locally via [[llama-cpp]].")},
            ]
            sample2_response = json.dumps({"edits": sample2_edits, "log_note": "Ingested sample2.md"})

            # Use the source path as the key for matching
            client = FakeLLMClient({
                "raw/sample1.md": sample1_response,
                "raw/sample2.md": sample2_response,
            })
            original_get_client = ingest_module.get_llm_client
            ingest_module.get_llm_client = lambda: client

            try:
                # Ingest first fixture
                ingest_source("raw/sample1.md")

                # Ingest second fixture
                ingest_source("raw/sample2.md")
            finally:
                ingest_module.get_llm_client = original_get_client

            # Query with --save
            query_client = FakeLLMClient({
                "select up to": '["openai", "llama-cpp", "ollama", "quantization", "llama-3", "meta"]',
                "Answer the question using ONLY": "For local inference, [[ollama]] provides a user-friendly interface over [[llama-cpp]], while [[llamafile]] offers single-file distribution. [[quantization]] to Q4_K_M enables running [[llama-3]] on consumer hardware."
            })
            original_query_client = query_module.get_llm_client
            query_module.get_llm_client = lambda: query_client

            try:
                answer = query_wiki("How to run Llama 3 locally?", save_slug="local-llama3-guide")
            finally:
                query_module.get_llm_client = original_query_client

            # Lint
            findings, exit_code = lint_wiki()

            # Verify files exist
            assert Path("wiki/sources/sample1.md").exists()
            assert Path("wiki/sources/sample2.md").exists()
            assert Path("wiki/entities/openai.md").exists()
            assert Path("wiki/entities/llama-3.md").exists()
            assert Path("wiki/entities/meta.md").exists()
            assert Path("wiki/concepts/quantization.md").exists()
            assert Path("wiki/comparisons/local-llama3-guide.md").exists()

            # Verify index updated
            index_fm, index_body = read_page("index.md")
            assert "sample1" in index_body
            assert "sample2" in index_body
            assert "local-llama3-guide" in index_body

            # Verify log has entries
            log_fm, log_body = read_page("log.md")
            assert "ingest | The Future of AI" in log_body
            assert "ingest | Local LLMs" in log_body
            assert "query | How to run Llama 3 locally?" in log_body
            assert "lint | report" in log_body

            print("E2E test passed!")
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)