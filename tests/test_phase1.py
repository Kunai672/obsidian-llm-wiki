"""
Phase 1 tests: scaffold and schema.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from llmwiki.wiki import init_wiki, list_pages, read_page


def test_init_creates_folders_and_seed_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            # Check folders exist
            assert (Path("wiki") / "sources").exists()
            assert (Path("wiki") / "entities").exists()
            assert (Path("wiki") / "concepts").exists()
            assert (Path("wiki") / "comparisons").exists()

            # Check seed files exist
            assert (Path("wiki") / "index.md").exists()
            assert (Path("wiki") / "log.md").exists()
            assert (Path("wiki") / "overview.md").exists()

            # Check index.md has correct structure
            fm, body = read_page("index.md")
            assert fm["title"] == "Index"
            assert fm["type"] == "other"
            # Initially only 'Other' section should appear (for index, log, overview)
            assert "Other" in body
            assert "Sources" not in body
            assert "Entities" not in body
            assert "Concepts" not in body
            assert "Comparisons" not in body

            # Check log.md has init entry
            fm, body = read_page("log.md")
            assert fm["title"] == "Log"
            assert "init | Initial wiki creation" in body

            # Check overview.md
            fm, body = read_page("overview.md")
            assert fm["title"] == "Overview"
            assert fm["type"] == "overview"
        finally:
            os.chdir(orig_cwd)


def test_init_idempotent_does_not_overwrite():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            # Modify index.md
            index_path = Path("wiki") / "index.md"
            original_content = index_path.read_text()
            index_path.write_text(original_content + "\n# MODIFIED\n")

            # Run init again
            init_wiki()

            # Content should be unchanged (not overwritten)
            new_content = index_path.read_text()
            assert new_content == original_content + "\n# MODIFIED\n"
        finally:
            os.chdir(orig_cwd)


def test_raw_folder_exists():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()
            assert (Path("raw") / "assets").exists()
        finally:
            os.chdir(orig_cwd)