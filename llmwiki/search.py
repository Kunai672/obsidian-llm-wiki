"""
Search command: BM25-style keyword ranking over wiki pages.
"""
from __future__ import annotations

import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .wiki import (
    init_wiki,
    list_pages,
    read_page,
    _wiki_root,
)
from .llm import get_llm_client


def _tokenize(text: str) -> list[str]:
    """Simple tokenization: lowercase, alphanumeric only."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _compute_bm25(query_terms: list[str], pages: list[tuple[Path, dict, str]], k1: float = 1.5, b: float = 0.75) -> list[tuple[float, Path, str]]:
    """Compute BM25 scores for pages against query terms."""
    if not pages:
        return []

    # Document frequencies
    N = len(pages)
    doc_freq = Counter()
    doc_lengths = {}
    page_tokens = {}

    for page, fm, body in pages:
        # Combine title, summary, tags, and body for search
        searchable_text = " ".join([
            fm.get("title", ""),
            fm.get("summary", ""),
            " ".join(fm.get("tags", [])),
            body,
        ])
        tokens = _tokenize(searchable_text)
        page_tokens[page] = tokens
        doc_lengths[page] = len(tokens)
        unique_tokens = set(tokens)
        for term in unique_tokens:
            doc_freq[term] += 1

    # Average document length
    avg_dl = sum(doc_lengths.values()) / N if N > 0 else 0

    # Score each page
    results = []
    for page, fm, body in pages:
        tokens = page_tokens[page]
        dl = doc_lengths[page]
        term_counts = Counter(tokens)

        score = 0.0
        for term in query_terms:
            if term not in term_counts:
                continue
            tf = term_counts[term]
            df = doc_freq[term]
            idf = math.log((N - df + 0.5) / (df + 0.5) + 1)
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))

        if score > 0:
            # Create snippet
            snippet = _make_snippet(body, query_terms)
            results.append((score, page, snippet))

    # Sort by score descending
    results.sort(key=lambda x: x[0], reverse=True)
    return results


def _make_snippet(body: str, query_terms: list[str], max_len: int = 200) -> str:
    """Create a snippet showing query terms in context."""
    if not body:
        return ""
    # Find first occurrence of any query term
    body_lower = body.lower()
    best_pos = len(body)
    for term in query_terms:
        pos = body_lower.find(term.lower())
        if pos != -1 and pos < best_pos:
            best_pos = pos

    start = max(0, best_pos - 50)
    end = min(len(body), start + max_len)
    snippet = body[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(body):
        snippet = snippet + "..."
    return snippet


def search_wiki(query: str, top_k: int = 10) -> list[tuple[str, str, str]]:
    """Search wiki pages using BM25. Returns list of (path, title, snippet)."""
    pages = list_pages()
    if not pages:
        return []

    # Load all pages
    page_data = []
    for page in pages:
        try:
            fm, body = read_page(page)
            page_data.append((page, fm, body))
        except Exception:
            continue

    query_terms = _tokenize(query)
    if not query_terms:
        return []

    results = _compute_bm25(query_terms, page_data)
    return [(str(page), fm.get("title", page.stem), snippet) for score, page, snippet in results[:top_k]]


def cmd_search(args: list[str]) -> int:
    """CLI entry for search command."""
    if not args:
        print("Usage: python -m llmwiki search \"<terms>\"", file=sys.stderr)
        return 1

    query = " ".join(args)
    try:
        init_wiki()
        results = search_wiki(query)
        if not results:
            print("No results found.")
            return 0

        for path, title, snippet in results:
            print(f"{path} — {title}")
            if snippet:
                print(f"  {snippet}")
            print()
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1