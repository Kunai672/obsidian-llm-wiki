"""
Ingest command: read raw source, ask LLM for edits, apply them.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .wiki import (
    init_wiki,
    read_raw,
    list_pages,
    read_page,
    update_index,
    append_log,
    WikiError,
    _wiki_root,
    _raw_root,
)
from .llm import get_llm_client
from .edits import request_edits_with_retry, parse_edits_json, EditError


MAX_CHARS_PER_CALL = 12000
MAX_RELEVANT_PAGES = 8


def _build_ingest_prompt(source_path: str, source_text: str, index_md: str, relevant_pages: list[tuple[str, str]]) -> str:
    """Build the prompt for the LLM to generate edits from a source."""
    pages_text = ""
    for path, summary in relevant_pages:
        pages_text += f"- {path}: {summary}\n"

    return f"""You are maintaining an Obsidian-compatible markdown wiki. A new raw source has been added.

Raw source: {source_path}
---
{source_text}
---

Current wiki index:
{index_md}

Relevant existing pages (title/summary):
{pages_text}

Your task: Generate JSON edits to integrate this source into the wiki.

Requirements:
1. ALWAYS create a source summary page at `sources/{Path(source_path).stem}.md`
2. Create/update entity pages for key people, orgs, products mentioned
3. Create/update concept pages for key ideas, methods, terminology
4. Link pages together using [[wikilinks]] with the page filename stem
5. Update existing pages when the source adds new information
6. Use frontmatter: title, type (source|entity|concept|comparison|overview), summary, sources (list of raw filenames), tags (lowercase), updated (YYYY-MM-DD)

Return ONLY JSON in this format:
{{
  "edits": [
    {{"path": "sources/sample1.md", "action": "create", "content": "---frontmatter---\\n\\nBody with [[links]]"}},
    {{"path": "entities/openai.md", "action": "create", "content": "---frontmatter---\\n\\nBody"}}
  ],
  "log_note": "Created source summary and 3 entity pages from sample1.md"
}}"""


def _find_relevant_pages(source_text: str, max_pages: int = MAX_RELEVANT_PAGES) -> list[tuple[str, str]]:
    """Find existing wiki pages whose titles/tags overlap with source text (keyword match)."""
    pages = list_pages()
    if not pages:
        return []

    # Simple keyword extraction from source (words > 3 chars, lowercase)
    words = set(w.lower() for w in source_text.split() if len(w) > 3 and w.isalpha())

    scored = []
    for page in pages:
        fm, _ = read_page(page)
        title = fm.get("title", "").lower()
        tags = [t.lower() for t in fm.get("tags", [])]
        summary = fm.get("summary", "").lower()

        # Score based on keyword overlap
        score = 0
        for word in words:
            if word in title:
                score += 3
            if word in summary:
                score += 2
            if word in tags:
                score += 1

        if score > 0:
            scored.append((score, page.stem, fm.get("summary", "")))

    scored.sort(reverse=True, key=lambda x: x[0])
    return [(stem, summary) for _, stem, summary in scored[:max_pages]]


def ingest_source(source_path: str, dry_run: bool = False) -> list[str]:
    """Ingest a raw source file into the wiki. Returns list of changed pages."""
    # Read raw source
    source_text = read_raw(source_path)
    if len(source_text) > MAX_CHARS_PER_CALL:
        # Truncate for prompt (in real use, would chunk and merge)
        source_text = source_text[:MAX_CHARS_PER_CALL] + "\n... [truncated]"

    # Load index and find relevant pages
    index_path = _wiki_root() / "index.md"
    index_md = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    relevant_pages = _find_relevant_pages(source_text)

    # Build prompt and request edits
    prompt = _build_ingest_prompt(source_path, source_text, index_md, relevant_pages)
    system = "You are a precise wiki editor. Output ONLY valid JSON as specified."

    client = get_llm_client()
    edits, log_note = request_edits_with_retry(client, system, prompt)

    if dry_run:
        print("DRY RUN - Proposed edits:")
        for edit in edits:
            print(f"  {edit['action']}: {edit['path']}")
        return []

    # Apply edits
    from .edits import apply_edits
    changed = apply_edits(edits)

    # Log the ingest
    source_stem = Path(source_path).stem
    # Get the source page title for log
    source_title = source_stem
    try:
        fm, _ = read_page(f"sources/{source_stem}.md")
        source_title = fm.get("title", source_stem)
    except WikiError:
        pass

    append_log("ingest", source_title, log_note or f"Ingested {source_path}")

    print(f"Ingested {source_path}")
    print(f"Changed pages: {', '.join(changed) if changed else '(none)'}")
    return changed


def cmd_ingest(args: list[str]) -> int:
    """CLI entry for ingest command."""
    if not args:
        print("Usage: python -m llmwiki ingest raw/<file> [--dry-run]", file=sys.stderr)
        return 1

    dry_run = "--dry-run" in args
    source_args = [a for a in args if a != "--dry-run"]

    if len(source_args) != 1:
        print("Usage: python -m llmwiki ingest raw/<file> [--dry-run]", file=sys.stderr)
        return 1

    source_path = source_args[0]
    if not source_path.startswith("raw/"):
        print("Source path must be under raw/", file=sys.stderr)
        return 1

    # Check file extension
    ext = Path(source_path).suffix.lower()
    if ext not in (".md", ".txt", ".markdown"):
        print(f"Unsupported file type: {ext}. Supported: .md, .txt", file=sys.stderr)
        return 1

    try:
        init_wiki()
        ingest_source(source_path, dry_run=dry_run)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1