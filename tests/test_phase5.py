"""
Phase 5 tests: query and file-back.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from llmwiki.query import query_wiki, cmd_query
from llmwiki.llm import FakeLLMClient
from llmwiki.wiki import init_wiki, read_page, list_pages, write_page, update_index
from llmwiki.ingest import ingest_source
import llmwiki.ingest as ingest_module
import llmwiki.query as query_module


def make_page_content(title: str, ptype: str, summary: str, sources: list[str], tags: list[str], updated: str, body: str) -> str:
    """Helper to create properly formatted page content."""
    import yaml
    fm = {
        "title": title,
        "type": ptype,
        "summary": summary,
        "sources": sources,
        "tags": tags,
        "updated": updated,
    }
    yaml_str = yaml.dump(fm, sort_keys=False).strip()
    return f"---\n{yaml_str}\n---\n\n{body}"


def setup_fake_backend():
    """Set up environment for fake LLM backend."""
    os.environ["LLMWIKI_BACKEND"] = "fake"


def teardown_fake_backend():
    """Restore environment."""
    os.environ.pop("LLMWIKI_BACKEND", None)


def test_query_empty_wiki():
    """Test query on empty wiki returns friendly message."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            answer = query_wiki("What is AI?")
            # The code returns "No relevant pages found for this question." when index is empty but LLM returns empty list
            assert "relevant pages" in answer.lower() or "empty" in answer.lower() or "init" in answer.lower()
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_query_with_fake_llm():
    """Test query returns answer with citations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Create some pages manually
            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI research company", "sources": ["raw/sample1.md"], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI created GPT-4 and ChatGPT.")
            write_page("entities/gpt-4.md", {"title": "GPT-4", "type": "entity", "summary": "Large language model", "sources": ["raw/sample1.md"], "tags": ["ai", "llm"], "updated": "2025-01-15"}, "GPT-4 is a multimodal model from OpenAI.")
            update_index()

            # Fake LLM returns page stems then answer
            # Step 1 prompt contains "select up to", Step 2 prompt contains "Answer the question using ONLY"
            client = FakeLLMClient({
                "select up to": '["openai", "gpt-4"]',
                "Answer the question using ONLY": "OpenAI created [[gpt-4]], a powerful language model."
            })
            original_get_client = query_module.get_llm_client
            query_module.get_llm_client = lambda: client

            try:
                answer = query_wiki("Who created GPT-4?")
                assert "openai" in answer.lower() or "OpenAI" in answer
                assert "[[gpt-4]]" in answer or "[[openai]]" in answer
            finally:
                query_module.get_llm_client = original_get_client
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_query_save_creates_page():
    """Test --save creates a comparison page, updates index, appends log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Create pages
            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI research company", "sources": ["raw/sample1.md"], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI created GPT-4.")
            write_page("entities/gpt-4.md", {"title": "GPT-4", "type": "entity", "summary": "LLM", "sources": ["raw/sample1.md"], "tags": ["ai"], "updated": "2025-01-15"}, "GPT-4 is from OpenAI.")
            update_index()

            client = FakeLLMClient({
                "select up to": '["openai", "gpt-4"]',
                "Answer the question using ONLY": "OpenAI created [[gpt-4]]."
            })
            original_get_client = query_module.get_llm_client
            query_module.get_llm_client = lambda: client

            try:
                answer = query_wiki("Who created GPT-4?", save_slug="gpt4-creator")
            finally:
                query_module.get_llm_client = original_get_client

            # Check comparison page created
            fm, body = read_page("comparisons/gpt4-creator.md")
            assert fm["type"] == "comparison"
            # Title is generated from slug: "gpt4-creator" -> "Gpt4 Creator"
            assert "Gpt4 Creator" in fm["title"] or "gpt4-creator" in fm["title"]
            assert "OpenAI" in body

            # Check index updated
            index_fm, index_body = read_page("index.md")
            assert "gpt4-creator" in index_body or "Gpt4 Creator" in index_body

            # Check log has query entry
            log_fm, log_body = read_page("log.md")
            assert "query | Who created GPT-4?" in log_body
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_query_without_save_still_logs():
    """Test query without --save still appends to log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI research company", "sources": ["raw/sample1.md"], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI created GPT-4.")
            update_index()

            client = FakeLLMClient({
                "select up to": '["openai"]',
                "Answer the question using ONLY": "OpenAI is an AI company."
            })
            original_get_client = query_module.get_llm_client
            query_module.get_llm_client = lambda: client

            try:
                query_wiki("What is OpenAI?")
            finally:
                query_module.get_llm_client = original_get_client

            # Check log has query entry
            log_fm, log_body = read_page("log.md")
            assert "query | What is OpenAI?" in log_body
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_query_cli():
    """Test the query CLI command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI research company", "sources": ["raw/sample1.md"], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI created GPT-4.")
            update_index()

            client = FakeLLMClient({
                "select up to": '["openai"]',
                "Answer the question using ONLY": "OpenAI is an AI research company."
            })
            original_get_client = query_module.get_llm_client
            query_module.get_llm_client = lambda: client

            try:
                # Test CLI
                result = cmd_query(["What is OpenAI?"])
                assert result == 0
            finally:
                query_module.get_llm_client = original_get_client
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)