# LLM Wiki

A local folder-based knowledge base where raw sources are immutable, an LLM-maintained wiki of interlinked markdown files sits on top of them, and a small CLI exposes ingest, query, and lint workflows.

## Quickstart

```bash
# Create and activate venv (no system pip needed)
python3 -m venv --without-pip .venv
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
.venv/bin/pip install pyyaml pytest

# Or install in development mode
.venv/bin/pip install -e .

# Initialize wiki
python -m llmwiki init

# Ingest a source (using fake LLM for testing)
LLMWIKI_BACKEND=fake python -m llmwiki ingest raw/sample.md

# Or with a real LLM (set env vars first)
export LLMWIKI_BASE_URL=http://localhost:8080/v1
export LLMWIKI_API_KEY=sk-xxx
export LLMWIKI_MODEL=llama3
python -m llmwiki ingest raw/sample.md

# Query the wiki
python -m llmwiki query "What is OpenAI?"

# Query and save as comparison page
python -m llmwiki query "Compare GPT-4 and Llama 3" --save gpt4-vs-llama3

# Lint the wiki
python -m llmwiki lint

# Search the wiki
python -m llmwiki search "OpenAI GPT-4"
```

## Installation

```bash
# Clone the repo
git clone https://github.com/yourusername/obsidian-llm-wiki
cd obsidian-llm-wiki

# Create venv without pip (for systems with broken ensurepip)
python3 -m venv --without-pip .venv
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python

# Install dependencies
.venv/bin/pip install pyyaml pytest

# Or install package in development mode
.venv/bin/pip install -e .
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `LLMWIKI_BACKEND` | LLM backend: `fake` (default) or `openai` | No |
| `LLMWIKI_BASE_URL` | Base URL for OpenAI-compatible API (e.g., `http://localhost:8080/v1`) | Yes (for openai backend) |
| `LLMWIKI_API_KEY` | API key for the LLM service | Yes (for openai backend) |
| `LLMWIKI_MODEL` | Model name to use (e.g., `llama3`, `gpt-4`) | Yes (for openai backend) |

### LLM Backends

- **fake** (default): Deterministic canned responses for testing. No network calls.
- **openai**: OpenAI-compatible API (llama.cpp server, NVIDIA NIM, Ollama, etc.). Uses `urllib` only, no SDK.

## Commands

| Command | Description |
|---------|-------------|
| `init` | Create wiki folders and seed files (idempotent) |
| `ingest raw/<file>` | Ingest a raw source (markdown/text) |
| `ingest raw/<file> --dry-run` | Show proposed edits without writing |
| `query "question"` | Answer a question using the wiki |
| `query "question" --save <slug>` | Answer and save as comparison page |
| `lint` | Check for broken links, orphans, missing frontmatter, etc. |
| `lint --deep` | Also use LLM to check for contradictions |
| `search "terms"` | BM25 keyword search over wiki pages |

## Project Structure

```
obsidian-llm-wiki/
├── AGENTS.md          # Schema & conventions for LLM agents
├── raw/               # Immutable source documents (read-only)
│   └── assets/        # Attachments (images, PDFs, etc.)
├── wiki/              # LLM-owned markdown pages
│   ├── index.md       # Content catalog (code-owned)
│   ├── log.md         # Append-only operation log (code-owned)
│   ├── overview.md    # High-level map
│   ├── lint-report.md # Latest lint report
│   ├── sources/       # Source summaries
│   ├── entities/      # People, orgs, products
│   ├── concepts/      # Ideas, methods, terminology
│   └── comparisons/   # Side-by-side analyses
├── llmwiki/           # Python package
├── fixtures/          # Sample raw documents
├── tests/             # Test suite
├── pyproject.toml     # Package config
└── README.md          # This file
```

## Using with Obsidian

Point Obsidian at the `wiki/` folder as a vault. All pages use:
- YAML frontmatter (`title`, `type`, `summary`, `sources`, `tags`, `updated`)
- Wikilinks: `[[page-stem]]` (filename without `.md`)
- Standard markdown

The `raw/assets/` folder can be used for attachments referenced from raw sources.

## Using AGENTS.md with an Interactive Agent

The `AGENTS.md` file at the repo root tells any LLM agent the structure, conventions, and workflows. When working with an interactive agent (Claude, GPT, etc.):

1. Give the agent access to the repo
2. Ask it to read `AGENTS.md` first
3. The agent can then ingest, query, and maintain the wiki following the documented conventions

## Troubleshooting

### "LLMWIKI_BASE_URL not set"
Set the environment variable for your LLM server:
```bash
export LLMWIKI_BASE_URL=http://localhost:8080/v1
export LLMWIKI_MODEL=llama3
```

### "Raw file not found"
Ensure the file exists under `raw/` and use the correct path:
```bash
python -m llmwiki ingest raw/my-doc.md
```

### "Unsupported file type"
Only `.md`, `.txt`, and `.markdown` files are supported for ingestion.

### Lint fails with "BROKEN_LINK"
Fix the wikilink in the page body to point to an existing page stem.

### Lint fails with "MISSING_FRONTMATTER"
Ensure all pages have the required frontmatter fields: `title`, `type`, `summary`, `sources`, `tags`, `updated`.

## Development

```bash
# Run tests
.venv/bin/pytest -q

# Run specific test phase
.venv/bin/pytest tests/test_phase4.py -q
```

## License

MIT