"""
Edit protocol: parse LLM JSON output, validate, apply atomically.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .wiki import (
    write_page,
    read_page,
    update_index,
    append_log,
    WikiError,
    PathSafetyError,
    _wiki_root,
    parse_frontmatter,
)


class EditError(WikiError):
    pass


EDIT_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_edits_json(text: str) -> dict[str, Any]:
    """Extract and parse JSON from LLM output, stripping code fences."""
    # Strip markdown code fences
    text = text.strip()
    if text.startswith("```"):
        # Remove first line (```json or ```)
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        # Remove last line if it's ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    # Try to find JSON object
    match = EDIT_JSON_RE.search(text)
    if not match:
        raise EditError(f"No JSON object found in LLM output: {text[:200]}")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise EditError(f"Invalid JSON in LLM output: {e}") from e


def validate_edit(edit: dict[str, Any]) -> tuple[str, str, str]:
    """Validate a single edit dict. Returns (path, action, content)."""
    path = edit.get("path")
    action = edit.get("action")
    content = edit.get("content")

    if not path or not isinstance(path, str):
        raise EditError("Edit missing 'path' field")
    if action not in ("create", "replace", "append"):
        raise EditError(f"Invalid action: {action}")
    if not content or not isinstance(content, str):
        raise EditError("Edit missing 'content' field")

    # Path safety: must be inside wiki/, not index.md or log.md
    if path.startswith("../") or path.startswith("/"):
        raise EditError(f"Path traversal not allowed: {path}")
    if path in ("index.md", "log.md") or path.startswith("index.md") or path.startswith("log.md"):
        raise EditError(f"Cannot edit code-owned file: {path}")

    # Content must have valid frontmatter
    fm, _ = parse_frontmatter(content)
    required_fields = ["title", "type", "summary", "sources", "tags", "updated"]
    for field in required_fields:
        if field not in fm:
            raise EditError(f"Content missing required frontmatter field: {field}")

    return path, action, content


def apply_edits(edits: list[dict[str, Any]]) -> list[str]:
    """Apply a list of edits atomically (all or none). Returns list of changed paths."""
    validated = []
    for edit in edits:
        path, action, content = validate_edit(edit)
        validated.append((path, action, content))

    # Apply all edits
    changed = []
    for path, action, content in validated:
        fm, body = parse_frontmatter(content)
        if action == "create":
            # Check if already exists
            try:
                read_page(path)
                raise EditError(f"Page already exists (use replace): {path}")
            except WikiError:
                pass
            write_page(path, fm, body)
            changed.append(path)
        elif action == "replace":
            write_page(path, fm, body)
            changed.append(path)
        elif action == "append":
            try:
                existing_fm, existing_body = read_page(path)
                # Merge frontmatter: keep existing, but update sources/tags if new ones
                merged_fm = existing_fm.copy()
                # Merge sources
                existing_sources = set(merged_fm.get("sources", []))
                new_sources = set(fm.get("sources", []))
                merged_fm["sources"] = sorted(existing_sources | new_sources)
                # Merge tags
                existing_tags = set(merged_fm.get("tags", []))
                new_tags = set(fm.get("tags", []))
                merged_fm["tags"] = sorted(existing_tags | new_tags)
                # Update title/type/summary from new content if provided
                for field in ("title", "type", "summary", "updated"):
                    if field in fm:
                        merged_fm[field] = fm[field]
                merged_body = existing_body + "\n\n" + body
                write_page(path, merged_fm, merged_body)
            except WikiError:
                # Page doesn't exist, create it
                write_page(path, fm, body)
            changed.append(path)

    # Regenerate index after all edits
    update_index()

    return changed


def request_edits_with_retry(
    client,
    system: str,
    prompt: str,
    max_retries: int = 1,
) -> tuple[list[dict[str, Any]], str]:
    """Request edits from LLM with one retry on failure."""
    last_error = None
    for attempt in range(max_retries + 1):
        response = client.complete(system, prompt)
        try:
            parsed = parse_edits_json(response)
            edits = parsed.get("edits", [])
            log_note = parsed.get("log_note", "")
            # Validate all edits before applying
            for edit in edits:
                validate_edit(edit)
            return edits, log_note
        except (EditError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < max_retries:
                # Retry with error appended
                prompt = f"{prompt}\n\nPREVIOUS ERROR: {e}\nPlease fix and return valid JSON only."
            else:
                raise EditError(f"LLM failed to produce valid edits after {max_retries + 1} attempts: {last_error}") from last_error

    raise EditError(f"LLM failed after retries: {last_error}")