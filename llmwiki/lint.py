"""
Lint command: deterministic checks for wiki consistency.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from .wiki import (
    init_wiki,
    list_pages,
    read_page,
    extract_links,
    resolve_link,
    update_index,
    append_log,
    write_page,
    _wiki_root,
    WikiError,
)
from .llm import get_llm_client


REQUIRED_FIELDS = ["title", "type", "summary", "sources", "tags", "updated"]
CODE_OWNED = {"index.md", "log.md", "overview.md", "lint-report.md"}


def lint_wiki(deep: bool = False, max_deep_pairs: int = 10) -> tuple[list[str], int]:
    """Run lint checks on the wiki.

    Returns:
        (findings, exit_code) where exit_code is 0 if clean, 1 if errors.
    """
    findings = []
    pages = list_pages()

    if not pages:
        return ["Wiki is empty"], 0

    # Load all pages
    page_data = {}
    for page in pages:
        try:
            fm, body = read_page(page)
            page_data[page] = (fm, body)
        except WikiError as e:
            findings.append(f"ERROR: Failed to read {page}: {e}")

    # 1. Broken links
    for page, (fm, body) in page_data.items():
        for link in extract_links(body):
            target = resolve_link(link)
            if target is None:
                findings.append(f"BROKEN_LINK: {page} -> [[{link}]] (target not found)")

    # 2. Orphan pages (no inbound links from non-code-owned pages)
    inbound = defaultdict(list)
    for page, (fm, body) in page_data.items():
        if page.name in CODE_OWNED:
            continue  # Skip code-owned pages as sources of inbound links
        for link in extract_links(body):
            target = resolve_link(link)
            if target:
                inbound[target].append(page)

    for page in page_data:
        if page not in inbound and page.name not in CODE_OWNED:
            findings.append(f"ORPHAN: {page} (no inbound links)")

    # 3. Pages missing from index
    index_path = _wiki_root() / "index.md"
    if index_path.exists():
        index_fm, index_body = read_page(index_path)
        # Parse index to find listed pages
        indexed_stems = set()
        import re
        for match in re.finditer(r"\[\[([^\]]+)\]\]", index_body):
            indexed_stems.add(match.group(1).lower())

        for page in page_data:
            stem = page.stem.lower()
            if stem not in indexed_stems and page.name not in CODE_OWNED:
                findings.append(f"MISSING_FROM_INDEX: {page} not listed in index.md")

    # 4. Index entries pointing to missing pages
    for stem in indexed_stems:
        if resolve_link(stem) is None:
            findings.append(f"INDEX_MISSING_PAGE: index.md references [[{stem}]] but page not found")

    # 5. Missing required frontmatter fields
    for page, (fm, body) in page_data.items():
        for field in REQUIRED_FIELDS:
            if field not in fm:
                findings.append(f"MISSING_FRONTMATTER: {page} missing required field '{field}'")

    # 6. Duplicate titles
    title_to_pages = defaultdict(list)
    for page, (fm, body) in page_data.items():
        title = fm.get("title", "")
        if title:
            title_to_pages[title].append(page)

    for title, page_list in title_to_pages.items():
        if len(page_list) > 1:
            findings.append(f"DUPLICATE_TITLE: '{title}' used by {', '.join(str(p) for p in page_list)}")

    # 7. [[bracket]] terms without a page (concepts mentioned but lacking a page)
    all_stems = {p.stem.lower() for p in pages}
    for page, (fm, body) in page_data.items():
        for link in extract_links(body):
            if link.lower() not in all_stems:
                findings.append(f"UNLINKED_CONCEPT: {page} references [[{link}]] but no page exists")

    # Deep checks with LLM (optional)
    if deep:
        deep_findings = _run_deep_lint(page_data, max_deep_pairs)
        findings.extend(deep_findings)

    # Write lint report
    _write_lint_report(findings)

    # Log the lint run
    append_log("lint", "report")

    # Determine exit code
    has_errors = any(f.startswith(("BROKEN_LINK:", "MISSING_FRONTMATTER:")) for f in findings)
    exit_code = 1 if has_errors else 0

    return findings, exit_code


def _run_deep_lint(page_data: dict, max_pairs: int) -> list[str]:
    """Run LLM-based deep lint checks on tag-sharing page pairs."""
    findings = []

    # Group pages by tags
    tag_to_pages = defaultdict(list)
    for page, (fm, body) in page_data.items():
        for tag in fm.get("tags", []):
            tag_to_pages[tag].append(page)

    # Find pairs sharing tags
    pairs = set()
    for tag, page_list in tag_to_pages.items():
        for i, p1 in enumerate(page_list):
            for p2 in page_list[i+1:]:
                pairs.add((p1, p2))

    pairs = list(pairs)[:max_pairs]

    if not pairs:
        return findings

    client = get_llm_client()
    system = "You are a precise fact-checker. Compare two wiki pages and report any contradictions or stale claims. Output ONLY a JSON list of issues, or empty list."

    for p1, p2 in pairs:
        fm1, body1 = page_data[p1]
        fm2, body2 = page_data[p2]

        prompt = f"""Compare these two wiki pages for contradictions or stale claims:

Page 1 ({p1.stem}):
Title: {fm1.get('title')}
Summary: {fm1.get('summary')}
Updated: {fm1.get('updated')}
Body: {body1[:2000]}

Page 2 ({p2.stem}):
Title: {fm2.get('title')}
Summary: {fm2.get('summary')}
Updated: {fm2.get('updated')}
Body: {body2[:2000]}

Return JSON array of issues, each with: {{"type": "contradiction|stale", "description": "...", "pages": ["{p1.stem}", "{p2.stem}"]}}"""

        try:
            response = client.complete(system, prompt)
            import json
            issues = json.loads(response.strip())
            for issue in issues:
                findings.append(f"DEEP_{issue['type'].upper()}: {issue['description']} (pages: {', '.join(issue['pages'])})")
        except Exception:
            pass  # Silently ignore deep lint errors

    return findings


def _write_lint_report(findings: list[str]) -> None:
    """Write lint report to wiki/lint-report.md."""
    from datetime import date
    import yaml

    today = date.today().isoformat()
    lines = [
        "---",
        'title: "Lint Report"',
        'type: "other"',
        f'summary: "Lint report from {today}"',
        "sources: []",
        "tags: [lint, report]",
        f'updated: "{today}"',
        "---",
        "",
        f"# Lint Report ({today})",
        "",
    ]

    if findings:
        lines.append("## Findings")
        lines.append("")
        for finding in findings:
            lines.append(f"- {finding}")
    else:
        lines.append("No issues found. Wiki is clean.")
    lines.append("")

    content = "\n".join(lines)
    fm = {
        "title": "Lint Report",
        "type": "other",
        "summary": f"Lint report from {today}",
        "sources": [],
        "tags": ["lint", "report"],
        "updated": today,
    }
    write_page("lint-report.md", fm, "\n".join(lines[10:]))  # Skip frontmatter in body
    update_index()


def cmd_lint(args: list[str]) -> int:
    """CLI entry for lint command."""
    deep = "--deep" in args

    try:
        init_wiki()
        findings, exit_code = lint_wiki(deep=deep)

        for finding in findings:
            print(finding)

        if exit_code == 0:
            print("Lint passed: no errors found.")
        else:
            print("Lint failed: errors found.", file=sys.stderr)

        return exit_code
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1