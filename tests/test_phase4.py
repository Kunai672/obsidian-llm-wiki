"""
Phase 4 tests: ingest command.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from llmwiki.ingest import ingest_source, cmd_ingest
from llmwiki.llm import FakeLLMClient
from llmwiki.wiki import init_wiki, read_page, list_pages, _wiki_root
from llmwiki.edits import apply_edits


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


def test_ingest_creates_source_summary():
    """Test that ingest creates a source summary page."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            # Create raw file
            raw_dir = Path("raw")
            raw_dir.mkdir(exist_ok=True)
            (raw_dir / "sample1.md").write_text("# Test Source\n\nThis is a test about OpenAI and GPT-4.")

            # Create fake LLM client that returns valid edits
            content = make_page_content(
                "Test Source", "source", "Summary of test source",
                ["raw/sample1.md"], ["test", "openai"], "2025-01-15",
                "This source discusses [[openai]] and [[gpt-4]]."
            )
            entity_content = make_page_content(
                "OpenAI", "entity", "AI research company",
                ["raw/sample1.md"], ["ai", "company"], "2025-01-15",
                "OpenAI created [[gpt-4]]."
            )
            response_json = json.dumps({
                "edits": [
                    {"path": "sources/sample1.md", "action": "create", "content": content},
                    {"path": "entities/openai.md", "action": "create", "content": entity_content},
                ],
                "log_note": "Created source summary and OpenAI entity"
            })
            client = FakeLLMClient({"sample1": response_json})

            # Monkey-patch get_llm_client
            import llmwiki.ingest as ingest_module
            original_get_client = ingest_module.get_llm_client
            ingest_module.get_llm_client = lambda: client

            try:
                changed = ingest_source("raw/sample1.md")
                assert "sources/sample1.md" in changed
                assert "entities/openai.md" in changed

                # Verify source page
                fm, body = read_page("sources/sample1.md")
                assert fm["title"] == "Test Source"
                assert fm["type"] == "source"
                assert "openai" in body.lower()

                # Verify entity page
                fm, body = read_page("entities/openai.md")
                assert fm["title"] == "OpenAI"
                assert fm["type"] == "entity"
            finally:
                ingest_module.get_llm_client = original_get_client
        finally:
            os.chdir(orig_cwd)


def test_ingest_updates_existing_page():
    """Test that re-ingesting updates rather than duplicates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            # Create raw file
            raw_dir = Path("raw")
            raw_dir.mkdir(exist_ok=True)
            (raw_dir / "sample1.md").write_text("# Test Source\n\nThis is a test about OpenAI.")

            # First ingest
            content1 = make_page_content(
                "Test Source", "source", "Summary v1",
                ["raw/sample1.md"], ["test"], "2025-01-15",
                "This source discusses [[openai]]."
            )
            entity_content1 = make_page_content(
                "OpenAI", "entity", "AI research company v1",
                ["raw/sample1.md"], ["ai"], "2025-01-15",
                "OpenAI creates models."
            )
            response_json1 = json.dumps({
                "edits": [
                    {"path": "sources/sample1.md", "action": "create", "content": content1},
                    {"path": "entities/openai.md", "action": "create", "content": entity_content1},
                ],
                "log_note": "First ingest"
            })

            # Second ingest (updated source)
            content2 = make_page_content(
                "Test Source", "source", "Summary v2",
                ["raw/sample1.md"], ["test"], "2025-01-16",
                "This source discusses [[openai]] and [[gpt-4]]."
            )
            entity_content2 = make_page_content(
                "OpenAI", "entity", "AI research company v2",
                ["raw/sample1.md"], ["ai", "gpt"], "2025-01-16",
                "OpenAI creates [[gpt-4]] and other models."
            )
            response_json2 = json.dumps({
                "edits": [
                    {"path": "sources/sample1.md", "action": "replace", "content": content2},
                    {"path": "entities/openai.md", "action": "replace", "content": entity_content2},
                ],
                "log_note": "Second ingest - updated"
            })

            import llmwiki.ingest as ingest_module
            client = FakeLLMClient({"sample1": response_json1})
            original_get_client = ingest_module.get_llm_client
            ingest_module.get_llm_client = lambda: client

            try:
                ingest_source("raw/sample1.md")
            finally:
                ingest_module.get_llm_client = original_get_client

            # Now second ingest
            client2 = FakeLLMClient({"sample1": response_json2})
            ingest_module.get_llm_client = lambda: client2
            try:
                changed = ingest_source("raw/sample1.md")
                assert "sources/sample1.md" in changed
                assert "entities/openai.md" in changed

                # Verify updated content
                fm, body = read_page("entities/openai.md")
                assert fm["summary"] == "AI research company v2"
                assert "gpt-4" in body
            finally:
                ingest_module.get_llm_client = original_get_client

            # Should not have duplicate pages
            pages = list_pages()
            openai_pages = [p for p in pages if p.stem == "openai"]
            assert len(openai_pages) == 1
        finally:
            os.chdir(orig_cwd)


def test_ingest_dry_run():
    """Test --dry-run prints proposed edits without writing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            raw_dir = Path("raw")
            raw_dir.mkdir(exist_ok=True)
            (raw_dir / "sample1.md").write_text("# Test Source\n\nContent.")

            content = make_page_content(
                "Test Source", "source", "Summary", ["raw/sample1.md"], [], "2025-01-15", "Body"
            )
            response_json = json.dumps({
                "edits": [{"path": "sources/sample1.md", "action": "create", "content": content}],
                "log_note": "Dry run test"
            })

            import llmwiki.ingest as ingest_module
            client = FakeLLMClient({"sample1": response_json})
            original_get_client = ingest_module.get_llm_client
            ingest_module.get_llm_client = lambda: client

            try:
                changed = ingest_source("raw/sample1.md", dry_run=True)
                assert changed == []  # dry run returns empty

                # No pages should be created
                pages = list_pages()
                source_pages = [p for p in pages if p.stem == "sample1"]
                assert len(source_pages) == 0
            finally:
                ingest_module.get_llm_client = original_get_client
        finally:
            os.chdir(orig_cwd)


def test_ingest_unsupported_type():
    """Test that unsupported file types are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            raw_dir = Path("raw")
            raw_dir.mkdir(exist_ok=True)
            (raw_dir / "sample1.pdf").write_text("PDF content")

            result = cmd_ingest(["raw/sample1.pdf"])
            assert result == 1
        finally:
            os.chdir(orig_cwd)


def test_raw_file_unchanged_after_ingest():
    """Test that raw file is byte-identical after ingest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            raw_dir = Path("raw")
            raw_dir.mkdir(exist_ok=True)
            original_content = "# Test Source\n\nThis is a test about OpenAI and GPT-4."
            (raw_dir / "sample1.md").write_text(original_content)

            content = make_page_content(
                "Test Source", "source", "Summary", ["raw/sample1.md"], ["test"], "2025-01-15", "Body"
            )
            response_json = json.dumps({
                "edits": [{"path": "sources/sample1.md", "action": "create", "content": content}],
                "log_note": "Test"
            })

            import llmwiki.ingest as ingest_module
            client = FakeLLMClient({"sample1": response_json})
            original_get_client = ingest_module.get_llm_client
            ingest_module.get_llm_client = lambda: client

            try:
                ingest_source("raw/sample1.md")

                # Verify raw file unchanged
                raw_content = (raw_dir / "sample1.md").read_text()
                assert raw_content == original_content
            finally:
                ingest_module.get_llm_client = original_get_client
        finally:
            os.chdir(orig_cwd)