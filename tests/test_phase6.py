"""
Phase 6 tests: lint command.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from llmwiki.lint import lint_wiki, cmd_lint
from llmwiki.llm import FakeLLMClient
from llmwiki.wiki import init_wiki, write_page, read_page, update_index
import llmwiki.lint as lint_module


def setup_fake_backend():
    os.environ["LLMWIKI_BACKEND"] = "fake"


def teardown_fake_backend():
    os.environ.pop("LLMWIKI_BACKEND", None)


def test_lint_clean_wiki():
    """Test lint on clean wiki exits 0 (orphan is a warning, not error)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Create a clean page
            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI company", "sources": ["raw/sample1.md"], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI is an AI company.")
            update_index()

            findings, exit_code = lint_wiki()
            # Orphan is a warning, not an error, so exit_code should be 0
            assert exit_code == 0
            # Should have orphan warning (no other pages link to it)
            orphans = [f for f in findings if "ORPHAN" in f]
            assert len(orphans) == 1
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_lint_broken_link():
    """Test lint detects broken links."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Page with broken link
            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI company", "sources": ["raw/sample1.md"], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI created [[nonexistent-model]].")
            update_index()

            findings, exit_code = lint_wiki()
            assert exit_code == 1
            assert any("BROKEN_LINK" in f for f in findings)
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_lint_orphan_page():
    """Test lint detects orphan pages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Create page with no inbound links from other content pages
            write_page("entities/orphan.md", {"title": "Orphan", "type": "entity", "summary": "Orphan page", "sources": [], "tags": [], "updated": "2025-01-15"}, "This page has no links to it.")
            update_index()

            findings, exit_code = lint_wiki()
            # Orphan is a warning, not an error, so exit_code should be 0
            assert exit_code == 0
            assert any("ORPHAN" in f for f in findings)
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_lint_missing_from_index():
    """Test lint detects pages missing from index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Create page but don't update index
            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI company", "sources": ["raw/sample1.md"], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI is an AI company.")
            # Don't call update_index()

            findings, exit_code = lint_wiki()
            assert any("MISSING_FROM_INDEX" in f for f in findings)
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_lint_index_missing_page():
    """Test lint detects index entries pointing to missing pages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Manually create index with a reference to a non-existent page
            index_path = Path("wiki/index.md")
            index_content = index_path.read_text() + "\n- [[nonexistent]] — A missing page\n"
            index_path.write_text(index_content)

            findings, exit_code = lint_wiki()
            assert any("INDEX_MISSING_PAGE" in f for f in findings)
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_lint_missing_frontmatter():
    """Test lint detects missing frontmatter fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Create page with missing frontmatter field
            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI company"}, "OpenAI is an AI company.")  # missing sources, tags, updated
            update_index()

            findings, exit_code = lint_wiki()
            assert exit_code == 1
            assert any("MISSING_FRONTMATTER" in f for f in findings)
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_lint_duplicate_titles():
    """Test lint detects duplicate titles."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Create two pages with same title
            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI company", "sources": ["raw/sample1.md"], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI is an AI company.")
            write_page("entities/openai2.md", {"title": "OpenAI", "type": "entity", "summary": "Another AI company", "sources": ["raw/sample2.md"], "tags": ["ai"], "updated": "2025-01-15"}, "Another OpenAI page.")
            update_index()

            findings, exit_code = lint_wiki()
            assert any("DUPLICATE_TITLE" in f for f in findings)
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_lint_unlinked_concept():
    """Test lint detects [[bracket]] terms without a page."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Page references a concept that doesn't exist as a page
            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI company", "sources": ["raw/sample1.md"], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI created [[gpt-5]] which doesn't exist yet.")
            update_index()

            findings, exit_code = lint_wiki()
            assert any("UNLINKED_CONCEPT" in f for f in findings)
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_lint_cli():
    """Test lint CLI command."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            write_page("entities/openai.md", {"title": "OpenAI", "type": "entity", "summary": "AI company", "sources": ["raw/sample1.md"], "tags": ["ai"], "updated": "2025-01-15"}, "OpenAI is an AI company.")
            update_index()

            result = cmd_lint([])
            assert result == 0
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)


def test_lint_fixture_scenario():
    """Test the acceptance scenario: one broken link + orphan pages + one missing-index page."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            setup_fake_backend()

            # Create a page with a broken link
            write_page("entities/page1.md", {"title": "Page 1", "type": "entity", "summary": "Page with broken link", "sources": [], "tags": [], "updated": "2025-01-15"}, "Links to [[missing-page]].")

            # Create an orphan page (no inbound links from other content pages)
            write_page("entities/orphan.md", {"title": "Orphan Page", "type": "entity", "summary": "Orphan", "sources": [], "tags": [], "updated": "2025-01-15"}, "No one links to me.")

            # Update index (includes page1 and orphan)
            update_index()

            # Create a page but don't add to index (create AFTER update_index)
            write_page("entities/missing-index.md", {"title": "Missing Index", "type": "entity", "summary": "Not in index", "sources": [], "tags": [], "updated": "2025-01-15"}, "I'm not in the index.")

            findings, exit_code = lint_wiki()

            # Should find exactly one broken link
            broken_links = [f for f in findings if "BROKEN_LINK" in f]
            assert len(broken_links) == 1, f"Expected 1 broken link, got {len(broken_links)}: {broken_links}"

            # Should find orphans (all three pages have no inbound links from other content pages)
            orphans = [f for f in findings if "ORPHAN" in f]
            assert len(orphans) == 3, f"Expected 3 orphans, got {len(orphans)}: {orphans}"

            # Should find one missing from index
            missing_index = [f for f in findings if "MISSING_FROM_INDEX" in f]
            assert len(missing_index) == 1, f"Expected 1 missing from index, got {len(missing_index)}: {missing_index}"

            # Exit code should be 1 due to broken link
            assert exit_code == 1
        finally:
            teardown_fake_backend()
            os.chdir(orig_cwd)