"""
Query command: read index, find relevant pages, answer with citations.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .wiki import (
    init_wiki,
    list_pages,
    read_page,
    update_index,
    append_log,
    _wiki_root,
    WikiError,
)
from .llm import get_llm_client
from .edits import request_edits_with_retry, EditError


MAX_RELEVANT_PAGES = 6


def _build_query_prompt_step1(question: str, index_md: str) -> str:
    """Step 1: Ask LLM to pick relevant page paths from index."""
    return f"""You are querying a wiki. Given a question and the wiki index, select up to {MAX_RELEVANT_PAGES} most relevant page paths.

Question: {question}

Wiki Index:
{index_md}

Return ONLY a JSON array of page stems (filenames without .md), e.g.:
["openai", "gpt-4", "local-llms", "quantization", "llama-cpp", "ollama"]"""


def _build_query_prompt_step2(question: str, pages_content: str) -> str:
    """Step 2: Ask LLM to answer the question citing pages."""
    return f"""Answer the question using ONLY the provided wiki pages. Cite sources using [[wikilink]] format with the page stem.

Question: {question}

Wiki Pages:
{pages_content}

Provide a clear, concise answer with inline citations like [[openai]]. If the wiki doesn't contain enough information, say so."""


def _load_pages_content(page_stems: list[str]) -> str:
    """Load full content of pages by stem."""
    pages = list_pages()
    stem_to_page = {p.stem: p for p in pages}

    content_parts = []
    for stem in page_stems:
        if stem in stem_to_page:
            fm, body = read_page(stem_to_page[stem])
            content_parts.append(f"--- Page: {stem} ---\n{body}")
        else:
            content_parts.append(f"--- Page: {stem} ---\n[PAGE NOT FOUND]")

    return "\n\n".join(content_parts)


def query_wiki(question: str, save_slug: str | None = None) -> str:
    """Query the wiki and optionally save the answer."""
    # Load index
    index_path = _wiki_root() / "index.md"
    index_md = index_path.read_text(encoding="utf-8") if index_path.exists() else ""

    if not index_md.strip():
        return "Wiki is empty. Run 'init' and 'ingest' first."

    # Step 1: Get relevant page stems
    client = get_llm_client()
    system = "You are a precise wiki query engine. Output ONLY valid JSON."
    prompt1 = _build_query_prompt_step1(question, index_md)

    try:
        response1 = client.complete(system, prompt1)
        # Parse JSON array
        page_stems = json.loads(response1.strip())
        if not isinstance(page_stems, list):
            page_stems = []
    except (json.JSONDecodeError, EditError):
        page_stems = []

    # Limit to max pages
    page_stems = page_stems[:MAX_RELEVANT_PAGES]

    if not page_stems:
        return "No relevant pages found for this question."

    # Step 2: Load pages and get answer
    pages_content = _load_pages_content(page_stems)
    prompt2 = _build_query_prompt_step2(question, pages_content)

    try:
        answer = client.complete(system, prompt2)
    except Exception as e:
        return f"Error generating answer: {e}"

    # Save if requested
    if save_slug:
        # Build sources list from cited pages
        cited_stems = set()
        import re
        for match in re.finditer(r"\[\[([^\]]+)\]\]", answer):
            cited_stems.add(match.group(1).lower())

        # Load full pages to get titles for sources
        sources = []
        for stem in cited_stems:
            if stem in {p.stem.lower() for p in list_pages()}:
                sources.append(f"raw/{stem}.md")  # approximate

        # Create comparison page
        from .wiki import write_page
        import yaml
        from datetime import date

        fm = {
            "title": save_slug.replace("-", " ").title(),
            "type": "comparison",
            "summary": f"Answer to: {question}",
            "sources": sources,
            "tags": ["query", "auto-generated"],
            "updated": date.today().isoformat(),
        }
        yaml_str = yaml.dump(fm, sort_keys=False).strip()
        content = f"---\n{yaml_str}\n---\n\n{answer}"

        write_page(f"comparisons/{save_slug}.md", fm, answer)
        update_index()
        append_log("query", question, f"Saved answer to comparisons/{save_slug}.md")
    else:
        append_log("query", question)

    return answer


def cmd_query(args: list[str]) -> int:
    """CLI entry for query command."""
    if not args:
        print("Usage: python -m llmwiki query \"question\" [--save <slug>]", file=sys.stderr)
        return 1

    save_slug = None
    question_parts = []
    i = 0
    while i < len(args):
        if args[i] == "--save" and i + 1 < len(args):
            save_slug = args[i + 1]
            i += 2
        else:
            question_parts.append(args[i])
            i += 1

    question = " ".join(question_parts)
    if not question:
        print("Usage: python -m llmwiki query \"question\" [--save <slug>]", file=sys.stderr)
        return 1

    try:
        init_wiki()
        answer = query_wiki(question, save_slug=save_slug)
        print(answer)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1