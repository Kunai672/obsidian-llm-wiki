# AGENTS.md — LLM Wiki Schema & Conventions

This file tells any LLM agent the structure, conventions, and workflows for the LLM Wiki system.

---

## 1. Three Layers

| Layer | Path | Ownership | Purpose |
|-------|------|-----------|---------|
| **Raw** | `raw/` (+ `raw/assets/`) | Human / ingestion tools | Immutable source documents. LLM **reads only**, never edits. |
| **Wiki** | `wiki/` | LLM (via CLI) | Interlinked markdown pages: source summaries, entities, concepts, comparisons, overview. Obsidian-compatible. |
| **Schema** | `AGENTS.md` (this file) | Human | The contract you are reading. |

### Wiki Subfolders
- `wiki/sources/` — one page per raw source (summary + metadata)
- `wiki/entities/` — people, orgs, products, projects, etc.
- `wiki/concepts/` — ideas, methods, terminology, frameworks
- `wiki/comparisons/` — side-by-side analyses, trade-off tables
- `wiki/` root — `index.md`, `log.md`, `overview.md`

---

## 2. Page Conventions

### Frontmatter (YAML, required on every wiki page)
```yaml
---
title: "Page Title"          # human-readable, unique across wiki
type: "source|entity|concept|comparison|overview|other"
summary: "One-line summary"  # used in index.md
sources:                     # list of raw source filenames that support this page
  - "raw/filename.md"
tags:                        # lowercase keywords for discovery
  - "tag1"
  - "tag2"
updated: "2025-01-15"        # ISO date of last edit
---
```

### Links
- Use **Obsidian wikilinks**: `[[page-filename]]` where `page-filename` is the **unique stem** (filename without `.md`).
- Example: `wiki/entities/acme-corp.md` → `[[acme-corp]]`
- Never use relative paths or `.md` inside brackets.
- Links are case-insensitive for resolution; store stems lowercase.

### File Naming
- Lowercase, kebab-case, unique stem across all wiki subfolders.
- Stem = filename without `.md` = the wikilink target.

---

## 3. Special Files (Code-Owned Only)

### `wiki/index.md` — Content Catalog
- **Written ONLY by code** (never by LLM edits).
- Groups every page by `type`: Sources, Entities, Concepts, Comparisons, Other.
- Each entry: `- [[stem]] — summary` (summary from frontmatter).
- Regenerated on every ingest/query/lint that changes pages.

### `wiki/log.md` — Append-Only Chronological Log
- **Written ONLY by code**.
- Each entry begins with exact prefix:
  ```
  ## [YYYY-MM-DD] <op> | <title>
  ```
  where `<op>` ∈ `{ingest, query, lint}`.
- Example: `## [2025-01-15] ingest | The Future of AI`
- Body follows (free-form, typically a bullet list of changed pages).
- `grep "^## \[" wiki/log.md | tail -5` must work.

### `wiki/overview.md` — High-Level Map
- Created by `init`, updated on ingest.
- Human-readable map of the knowledge base: major entities, concepts, and how they relate.
- Frontmatter `type: overview`.

---

## 4. Workflows (Plain Steps)

### Ingest (`python -m llmwiki ingest raw/<file>`)
1. Read raw source file (markdown or plain text).
2. Load `AGENTS.md` conventions, current `wiki/index.md`, and up to 8 existing wiki pages whose titles/tags overlap with the source (keyword match).
3. Ask LLM for edits via the **Edit Protocol** (see §5).
4. LLM must produce a **source summary page** in `wiki/sources/<stem>.md`.
5. LLM should create/update entity/concept pages (5–15 pages typical per source).
6. Apply all edits atomically (all-or-none).
7. Regenerate `wiki/index.md`.
8. Append log entry: `## [YYYY-MM-DD] ingest | <source title>`.
9. Print created/updated page paths.
10. `--dry-run` prints proposed edits without writing.

### Query (`python -m llmwiki query "question" [--save <slug>]`)
1. Read `wiki/index.md`.
2. Step 1: Ask LLM to pick up to 6 relevant page paths from index (JSON list).
3. Step 2: Load those pages, ask LLM to answer citing `[[wikilink]]`.
4. Print answer.
5. If `--save <slug>`: write answer to `wiki/comparisons/<slug>.md` with frontmatter `type: comparison`, `sources: [cited pages]`, regenerate index, append log `query | <question>`.
6. Without `--save`: still append log `query | <question>`.

### Lint (`python -m llmwiki lint [--deep]`)
Deterministic checks (no LLM):
- Broken wikilinks (target page missing).
- Orphan pages (no inbound links from any other page).
- Pages missing from `index.md`.
- Index entries pointing to missing pages.
- Missing required frontmatter fields (`title`, `type`, `summary`, `sources`, `tags`, `updated`).
- Duplicate titles across wiki.
- `[[bracket]]` terms in body that have no corresponding page.

`--deep`: additionally use LLM on tag-sharing page pairs (max 10 pairs) to detect contradictions/stale claims.

Output: write `wiki/lint-report.md` (replaced each run, listed in index under Other), append log `lint | report`.
Exit code: 0 if clean, 1 if broken links or missing frontmatter found.

---

## 5. Edit Protocol (LLM → Code)

LLM returns **JSON only** (no prose, no code fences):
```json
{
  "edits": [
    {
      "path": "entities/acme-corp.md",
      "action": "create|replace|append",
      "content": "---\ntitle: \"Acme Corp\"\ntype: entity\nsummary: \"...\"\nsources: [\"raw/source1.md\"]\ntags: [\"corp\", \"ai\"]\nupdated: \"2025-01-15\"\n---\n\nBody text with [[links]]."
    }
  ],
  "log_note": "Created Acme Corp entity from source1.md"
}
```

**Validation rules (code enforces):**
- `path` must be inside `wiki/` (no `..`, no absolute paths).
- `path` must not be `index.md` or `log.md`.
- `action` ∈ `{create, replace, append}`.
- `content` must have valid frontmatter with all required fields.
- All edits applied atomically (temp files + rename); on any failure, roll back all.

**Retry:** On invalid JSON or validation error, retry once with the error message appended to the prompt. Then raise a clear error.

---

## 6. LLM Client Interface

```python
class LLMClient:
    def complete(self, system: str, prompt: str) -> str: ...
```

Two implementations:
- `OpenAICompatibleClient` — uses `urllib` + env vars `LLMWIKI_BASE_URL`, `LLMWIKI_API_KEY`, `LLMWIKI_MODEL`. No SDK.
- `FakeLLMClient` — deterministic canned responses for tests (selected by `LLMWIKI_BACKEND=fake`).

**Prompts:** Keep short, one task per call, structured output (JSON). No network in tests.

---

## 7. CLI Commands

| Command | Description |
|---------|-------------|
| `python -m llmwiki init` | Create folders + seed `index.md`, `log.md`, `overview.md`. Idempotent. |
| `python -m llmwiki ingest raw/<file> [--dry-run]` | Ingest a raw source. |
| `python -m llmwiki query "question" [--save <slug>]` | Query the wiki. |
| `python -m llmwiki lint [--deep]` | Lint the wiki. |
| `python -m llmwiki search "<terms>"` | Keyword search (BM25) over wiki pages. |

---

## 8. Constraints & Invariants

- `raw/` is **read-only** to ALL code paths.
- `index.md` and `log.md` are written **only by code**, never by LLM edits.
- All LLM calls go through `LLMClient`; tests use `FakeLLMClient` (no network).
- Stdlib + `pyyaml` + `pytest` only. No vector DBs, embeddings, web frameworks, LLM SDKs.
- Modules ≤ ~300 lines.
- Never read/print/log/commit any API key.