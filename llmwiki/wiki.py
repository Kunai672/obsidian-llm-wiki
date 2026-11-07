"""
Wiki core library: frontmatter, links, backlinks, log, index.
"""
from __future__ import annotations

import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import yaml


def _wiki_root() -> Path:
    return Path("wiki").resolve()


def _raw_root() -> Path:
    return Path("raw").resolve()


class WikiError(Exception):
    pass


class PathSafetyError(WikiError):
    pass


def _ensure_wiki_root() -> None:
    root = _wiki_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "sources").mkdir(exist_ok=True)
    (root / "entities").mkdir(exist_ok=True)
    (root / "concepts").mkdir(exist_ok=True)
    (root / "comparisons").mkdir(exist_ok=True)


def _ensure_raw_root() -> None:
    root = _raw_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "assets").mkdir(exist_ok=True)


def _resolve_wiki_path(path: str | Path) -> Path:
    """Resolve a path to be within wiki root, raise if outside."""
    target = (_wiki_root() / path).resolve()
    try:
        target.relative_to(_wiki_root())
    except ValueError:
        raise PathSafetyError(f"Path {path} escapes wiki root")
    return target


def _resolve_raw_path(path: str | Path) -> Path:
    """Resolve a path to be within raw root, raise if outside."""
    target = (_raw_root() / path).resolve()
    try:
        target.relative_to(_raw_root())
    except ValueError:
        raise PathSafetyError(f"Path {path} escapes raw root")
    return target


def read_raw(path: str) -> str:
    """Read a raw source file (markdown or text). Accepts paths with or without 'raw/' prefix."""
    # Strip 'raw/' prefix if present
    if path.startswith("raw/"):
        path = path[4:]
    p = _resolve_raw_path(path)
    if not p.exists():
        raise WikiError(f"Raw file not found: {path}")
    return p.read_text(encoding="utf-8")


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and body. Returns (frontmatter_dict, body)."""
    m = FRONTMATTER_RE.match(text.strip())
    if not m:
        return {}, text
    fm_text, body = m.groups()
    fm = yaml.safe_load(fm_text) or {}
    return fm, body.strip()


def write_frontmatter(fm: dict[str, Any], body: str) -> str:
    """Serialize frontmatter + body to markdown string."""
    yaml_str = yaml.dump(fm, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{yaml_str}\n---\n\n{body.strip()}\n"


def read_page(path: str | Path) -> tuple[dict[str, Any], str]:
    """Read a wiki page, return (frontmatter, body)."""
    p = _resolve_wiki_path(path)
    if not p.exists():
        raise WikiError(f"Page not found: {path}")
    text = p.read_text(encoding="utf-8")
    return parse_frontmatter(text)


def write_page(path: str | Path, fm: dict[str, Any], body: str) -> None:
    """Atomically write a wiki page (temp + rename)."""
    target = _resolve_wiki_path(path)
    if target.name in ("index.md", "log.md"):
        raise WikiError(f"Cannot write to code-owned file: {target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    content = write_frontmatter(fm, body)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=target.parent, delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        tmp_path.replace(target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def list_pages() -> list[Path]:
    """List all wiki page paths (relative to wiki root)."""
    root = _wiki_root()
    if not root.exists():
        return []
    pages = []
    for ext in ("*.md", "*.markdown"):
        pages.extend(root.rglob(ext))
    return sorted(p.relative_to(root) for p in pages)


def resolve_link(link: str) -> Path | None:
    """Resolve a wikilink stem to a page path (relative to wiki root)."""
    stem = link.strip().lower()
    for page in list_pages():
        if page.stem.lower() == stem:
            return page
    return None


def extract_links(text: str) -> list[str]:
    """Extract all wikilink targets from text."""
    return [m.group(1) for m in WIKILINK_RE.finditer(text)]


def get_backlinks(target_stem: str) -> list[Path]:
    """Return pages that link to the given stem."""
    target = target_stem.lower()
    backlinks = []
    for page in list_pages():
        fm, body = read_page(page)
        for link in extract_links(body):
            if link.lower() == target:
                backlinks.append(page)
                break
    return backlinks


def append_log(op: str, title: str, body: str = "") -> None:
    """Append an entry to wiki/log.md with the exact prefix format."""
    today = date.today().isoformat()
    entry = f"## [{today}] {op} | {title}\n"
    if body:
        entry += f"{body.strip()}\n"
    entry += "\n"
    log_path = _wiki_root() / "log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


def update_index() -> None:
    """Regenerate wiki/index.md from all pages."""
    pages = list_pages()
    by_type: dict[str, list[tuple[str, str, Path]]] = {
        "source": [],
        "entity": [],
        "concept": [],
        "comparison": [],
        "overview": [],
        "other": [],
    }
    for page in pages:
        fm, _ = read_page(page)
        ptype = fm.get("type", "other")
        title = fm.get("title", page.stem)
        summary = fm.get("summary", "")
        if ptype not in by_type:
            ptype = "other"
        by_type[ptype].append((title, summary, page))

    lines = [
        "---",
        'title: "Index"',
        'type: "other"',
        'summary: "Content catalog of all wiki pages"',
        "sources: []",
        "tags: []",
        f'updated: "{date.today().isoformat()}"',
        "---",
        "",
        "# Index",
        "",
        "Content catalog of all wiki pages, grouped by category.",
        "",
    ]

    type_order = [
        ("source", "Sources"),
        ("entity", "Entities"),
        ("concept", "Concepts"),
        ("comparison", "Comparisons"),
        ("overview", "Overview"),
        ("other", "Other"),
    ]

    for key, label in type_order:
        entries = by_type.get(key, [])
        if not entries and key != "other":
            continue
        lines.append(f"## {label}")
        lines.append("")
        if entries:
            for title, summary, page in sorted(entries, key=lambda x: x[0].lower()):
                stem = page.stem
                lines.append(f"- [[{stem}]] — {summary}")
        else:
            lines.append("*None*")
        lines.append("")

    index_path = _wiki_root() / "index.md"
    content = "\n".join(lines).rstrip() + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=index_path.parent, delete=False, suffix=".tmp"
    ) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        tmp_path.replace(index_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def init_wiki() -> None:
    """Create folders and seed index.md, log.md, overview.md. Idempotent."""
    _ensure_wiki_root()
    _ensure_raw_root()

    # index.md
    index_path = _wiki_root() / "index.md"
    if not index_path.exists():
        update_index()

    # log.md
    log_path = _wiki_root() / "log.md"
    if not log_path.exists():
        today = date.today().isoformat()
        log_path.write_text(
            f"---\ntitle: \"Log\"\ntype: \"other\"\nsummary: \"Append-only chronological log\"\nsources: []\ntags: []\nupdated: \"{today}\"\n---\n\n"
            f"# Log\n\nAppend-only chronological log of all operations.\n\n"
            f"## [{today}] init | Initial wiki creation\n\n"
            f"- Created wiki folders and seed files: index.md, log.md, overview.md\n\n",
            encoding="utf-8",
        )

    # overview.md
    overview_path = _wiki_root() / "overview.md"
    if not overview_path.exists():
        today = date.today().isoformat()
        overview_path.write_text(
            f"---\ntitle: \"Overview\"\ntype: \"overview\"\nsummary: \"High-level map of the knowledge base\"\nsources: []\ntags: []\nupdated: \"{today}\"\n---\n\n"
            f"# Overview\n\nHigh-level map of the knowledge base. This page is updated on each ingest to reflect major entities, concepts, and their relationships.\n\n"
            f"*No content yet. Run `python -m llmwiki ingest raw/<file>` to populate.*\n",
            encoding="utf-8",
        )