"""
Phase 3 tests: LLM client and edit protocol.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from llmwiki.llm import LLMClient, FakeLLMClient, OpenAICompatibleClient, get_llm_client
from llmwiki.edits import (
    parse_edits_json,
    validate_edit,
    apply_edits,
    request_edits_with_retry,
    EditError,
)
from llmwiki.wiki import init_wiki, write_page, read_page, WikiError


def make_page_content(title: str, ptype: str, summary: str, sources: list[str], tags: list[str], updated: str, body: str) -> str:
    """Helper to create properly formatted page content."""
    fm = {
        "title": title,
        "type": ptype,
        "summary": summary,
        "sources": sources,
        "tags": tags,
        "updated": updated,
    }
    import yaml
    yaml_str = yaml.dump(fm, sort_keys=False).strip()
    return f"---\n{yaml_str}\n---\n\n{body}"


def test_fake_llm_client():
    client = FakeLLMClient({"test": '{"edits": [], "log_note": "ok"}'})
    result = client.complete("system", "test prompt")
    assert result == '{"edits": [], "log_note": "ok"}'


def test_fake_llm_client_default():
    client = FakeLLMClient()
    result = client.complete("system", "unknown prompt")
    assert "No matching canned response" in result


def test_openai_client_missing_env():
    # Clear env vars
    old_base = os.environ.pop("LLMWIKI_BASE_URL", None)
    old_model = os.environ.pop("LLMWIKI_MODEL", None)
    try:
        with pytest.raises(ValueError):
            OpenAICompatibleClient()
    finally:
        if old_base:
            os.environ["LLMWIKI_BASE_URL"] = old_base
        if old_model:
            os.environ["LLMWIKI_MODEL"] = old_model


def test_parse_edits_json_valid():
    text = '{"edits": [{"path": "entities/foo.md", "action": "create", "content": "---"}]}'
    parsed = parse_edits_json(text)
    assert "edits" in parsed


def test_parse_edits_json_with_code_fence():
    text = '''```json
{"edits": [{"path": "entities/foo.md", "action": "create", "content": "---"}], "log_note": "test"}
```'''
    parsed = parse_edits_json(text)
    assert "edits" in parsed
    assert parsed["log_note"] == "test"


def test_parse_edits_json_invalid():
    with pytest.raises(EditError):
        parse_edits_json("not json at all")


def test_validate_edit_valid():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            content = make_page_content("Foo", "entity", "A foo", [], [], "2025-01-01", "Body")
            edit = {
                "path": "entities/foo.md",
                "action": "create",
                "content": content,
            }
            path, action, content_out = validate_edit(edit)
            assert path == "entities/foo.md"
            assert action == "create"
        finally:
            os.chdir(orig_cwd)


def test_validate_edit_invalid_action():
    with pytest.raises(EditError):
        validate_edit({"path": "entities/foo.md", "action": "delete", "content": "---"})


def test_validate_edit_path_traversal():
    with pytest.raises(EditError):
        validate_edit({"path": "../raw/foo.md", "action": "create", "content": "---"})


def test_validate_edit_index_log_rejected():
    with pytest.raises(EditError):
        validate_edit({"path": "index.md", "action": "create", "content": "---"})
    with pytest.raises(EditError):
        validate_edit({"path": "log.md", "action": "create", "content": "---"})


def test_validate_edit_missing_frontmatter_field():
    with pytest.raises(EditError):
        validate_edit({
            "path": "entities/foo.md",
            "action": "create",
            "content": "---\ntitle: Foo\n---\n\nBody",  # missing type, summary, etc.
        })


def test_apply_edits_create():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            content = make_page_content("Foo", "entity", "A foo", [], [], "2025-01-01", "Body")
            edits = [{
                "path": "entities/foo.md",
                "action": "create",
                "content": content,
            }]
            changed = apply_edits(edits)
            assert "entities/foo.md" in changed

            fm, body = read_page("entities/foo.md")
            assert fm["title"] == "Foo"
        finally:
            os.chdir(orig_cwd)


def test_apply_edits_replace():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            # Create initial
            write_page("entities/foo.md", {"title": "Foo", "type": "entity", "summary": "", "sources": [], "tags": [], "updated": "2025-01-01"}, "Old body")

            content = make_page_content("Foo", "entity", "Updated", [], [], "2025-01-02", "New body")
            edits = [{
                "path": "entities/foo.md",
                "action": "replace",
                "content": content,
            }]
            changed = apply_edits(edits)
            assert "entities/foo.md" in changed

            fm, body = read_page("entities/foo.md")
            assert fm["summary"] == "Updated"
            assert body == "New body"
        finally:
            os.chdir(orig_cwd)


def test_apply_edits_append():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            # Create initial
            write_page("entities/foo.md", {"title": "Foo", "type": "entity", "summary": "", "sources": ["raw/a.md"], "tags": ["tag1"], "updated": "2025-01-01"}, "Old body")

            content = make_page_content("Foo", "entity", "Updated", ["raw/b.md"], ["tag2"], "2025-01-02", "New section")
            edits = [{
                "path": "entities/foo.md",
                "action": "append",
                "content": content,
            }]
            changed = apply_edits(edits)
            assert "entities/foo.md" in changed

            fm, body = read_page("entities/foo.md")
            assert "raw/a.md" in fm["sources"]
            assert "raw/b.md" in fm["sources"]
            assert "tag1" in fm["tags"]
            assert "tag2" in fm["tags"]
            assert "Old body" in body
            assert "New section" in body
        finally:
            os.chdir(orig_cwd)


def test_apply_edits_all_or_none():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            # First edit valid, second invalid (missing frontmatter)
            content1 = make_page_content("Foo", "entity", "A foo", [], [], "2025-01-01", "Body")
            edits = [
                {
                    "path": "entities/foo.md",
                    "action": "create",
                    "content": content1,
                },
                {
                    "path": "entities/bar.md",
                    "action": "create",
                    "content": "---\ntitle: Bar\n---\n\nBody",  # missing required fields
                },
            ]
            with pytest.raises(EditError):
                apply_edits(edits)

            # First edit should not have been applied
            pages = list(Path("wiki").rglob("*.md"))
            page_stems = [p.stem for p in pages]
            assert "foo" not in page_stems
        finally:
            os.chdir(orig_cwd)


def test_request_edits_with_retry_success():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            content = make_page_content("Foo", "entity", "A foo", [], [], "2025-01-01", "Body")
            response_json = json.dumps({
                "edits": [{
                    "path": "entities/foo.md",
                    "action": "create",
                    "content": content,
                }],
                "log_note": "Created foo"
            })
            client = FakeLLMClient({"test": response_json})
            edits, log_note = request_edits_with_retry(client, "system", "test prompt")
            assert len(edits) == 1
            assert log_note == "Created foo"
        finally:
            os.chdir(orig_cwd)


def test_request_edits_with_retry_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            init_wiki()

            client = FakeLLMClient({"test": "not json"})
            with pytest.raises(EditError):
                request_edits_with_retry(client, "system", "test prompt", max_retries=1)
        finally:
            os.chdir(orig_cwd)