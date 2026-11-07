"""
Phase 2 tests: wiki core library.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pytest

from llmwiki.wiki import (
    init_wiki,
    list_pages,
    read_page,
    write_page,
    parse_frontmatter,
    write_frontmatter,
    resolve_link,
    extract_links,
    get_backlinks,
    append_log,
    update_index,
    read_raw,
    PathSafetyError,
    WikiError,
)


def test_frontmatter_round_trip():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            fm = {
                "title": "Test Page",
                "type": "entity",
                "summary": "A test entity",
                "sources": ["raw/test.md"],
                "tags": ["test", "entity"],
                "updated": "2025-01-15",
            }
            body = "This is the body with a [[link]]."
            write_page("entities/test-page.md", fm, body)

            read_fm, read_body = read_page("entities/test-page.md")
            assert read_fm == fm
            assert read_body == body
        finally:
            os.chdir(orig_cwd)


def test_parse_frontmatter():
    text = "---\ntitle: \"Test\"\ntype: entity\n---\n\nBody content."
    fm, body = parse_frontmatter(text)
    assert fm["title"] == "Test"
    assert fm["type"] == "entity"
    assert body == "Body content."


def test_write_frontmatter():
    fm = {"title": "Test", "type": "entity"}
    body = "Body content."
    result = write_frontmatter(fm, body)
    assert result.startswith("---\n")
    assert "title: Test" in result
    assert "type: entity" in result
    assert result.endswith("Body content.\n")


def test_link_resolution():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            fm = {"title": "Foo", "type": "entity", "summary": "", "sources": [], "tags": [], "updated": "2025-01-01"}
            write_page("entities/foo.md", fm, "Foo entity")

            # Test resolve_link
            resolved = resolve_link("foo")
            assert resolved is not None
            assert resolved.stem == "foo"

            # Test missing target
            missing = resolve_link("nonexistent")
            assert missing is None
        finally:
            os.chdir(orig_cwd)


def test_extract_links():
    text = "See [[foo]] and [[bar]] but not [regular link](http://example.com)."
    links = extract_links(text)
    assert links == ["foo", "bar"]


def test_backlinks():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            fm = {"title": "Target", "type": "entity", "summary": "", "sources": [], "tags": [], "updated": "2025-01-01"}
            write_page("entities/target.md", fm, "Target entity")

            fm2 = {"title": "Source", "type": "entity", "summary": "", "sources": [], "tags": [], "updated": "2025-01-01"}
            write_page("entities/source.md", fm2, "Source links to [[target]]")

            backlinks = get_backlinks("target")
            assert len(backlinks) == 1
            assert backlinks[0].stem == "source"
        finally:
            os.chdir(orig_cwd)


def test_log_prefix_format():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            append_log("ingest", "Test Source", "- Created page A\n- Updated page B")
            append_log("query", "What is foo?")
            append_log("lint", "report")

            log_path = Path("wiki") / "log.md"
            content = log_path.read_text()

            # Check prefix regex matches
            pattern = r"^## \[\d{4}-\d{2}-\d{2}\] (ingest|query|lint) \| .+"
            matches = re.findall(pattern, content, re.MULTILINE)
            assert len(matches) == 3
            assert matches[0] == "ingest"
            assert matches[1] == "query"
            assert matches[2] == "lint"
        finally:
            os.chdir(orig_cwd)


def test_index_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            # Run update_index twice
            update_index()
            index1 = Path("wiki/index.md").read_text()
            update_index()
            index2 = Path("wiki/index.md").read_text()

            assert index1 == index2
        finally:
            os.chdir(orig_cwd)


def test_raw_write_raises():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            # Create a raw file
            raw_path = Path("raw/test.md")
            raw_path.write_text("raw content")

            # read_raw should work
            content = read_raw("test.md")
            assert content == "raw content"

            # Writing to raw/ via wiki functions should raise
            # write_page should reject paths outside wiki
            fm = {"title": "Test", "type": "entity", "summary": "", "sources": [], "tags": [], "updated": "2025-01-01"}
            with pytest.raises(PathSafetyError):
                write_page("../raw/test.md", fm, "body")
        finally:
            os.chdir(orig_cwd)


def test_path_safety_wiki():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            # Try to escape wiki root via write_page
            fm = {"title": "Test", "type": "entity", "summary": "", "sources": [], "tags": [], "updated": "2025-01-01"}
            with pytest.raises(PathSafetyError):
                write_page("../raw/test.md", fm, "body")
        finally:
            os.chdir(orig_cwd)


def test_write_page_rejects_index_log():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            fm = {"title": "Test", "type": "entity", "summary": "", "sources": [], "tags": [], "updated": "2025-01-01"}

            with pytest.raises(WikiError):
                write_page("index.md", fm, "body")

            with pytest.raises(WikiError):
                write_page("log.md", fm, "body")
        finally:
            os.chdir(orig_cwd)