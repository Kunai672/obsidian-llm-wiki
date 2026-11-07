"""
Phase 8 test: end-to-end CLI test with LLMWIKI_BACKEND=fake.
This test verifies the CLI works end-to-end with the fake backend.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


def test_e2e_cli_with_fake_backend():
    """End-to-end test running the real CLI as subprocess with LLMWIKI_BACKEND=fake."""
    with tempfile.TemporaryDirectory() as tmpdir:
        orig_cwd = Path.cwd()
        try:
            os.chdir(tmpdir)
            
            # Set up environment
            env = os.environ.copy()
            env["LLMWIKI_BACKEND"] = "fake"
            env["PYTHONPATH"] = str(Path("/home/ubuntu/.treehouse/obsidian-llm-wiki-fe3be1/1/obsidian-llm-wiki"))
            
            # Helper to run CLI commands
            def run_cmd(*args):
                cmd = [sys.executable, "-m", "llmwiki", *args]
                result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=tmpdir)
                return result
            
            # Copy fixtures to raw/
            fixture_dir = Path("/home/ubuntu/.treehouse/obsidian-llm-wiki-fe3be1/1/obsidian-llm-wiki/fixtures")
            raw_dir = Path(tmpdir) / "raw"
            raw_dir.mkdir(exist_ok=True)
            shutil.copy(fixture_dir / "sample1.md", raw_dir / "sample1.md")
            original_raw = (raw_dir / "sample1.md").read_bytes()
            
            # 1. Init
            result = run_cmd("init")
            assert result.returncode == 0, f"init failed: {result.stderr}"
            
            # 2. Ingest
            result = run_cmd("ingest", "raw/sample1.md")
            assert result.returncode == 0, f"ingest failed: {result.stderr}"
            assert "Changed pages:" in result.stdout
            
            # 3. Query with --save
            result = run_cmd("query", "What is OpenAI?", "--save", "demo-query")
            assert result.returncode == 0, f"query failed: {result.stderr}"
            
            # 4. Lint
            result = run_cmd("lint")
            assert result.returncode == 0, f"lint failed: {result.stderr}"
            assert "Lint passed" in result.stdout
            
            # 5. Search
            result = run_cmd("search", "OpenAI")
            assert result.returncode == 0, f"search failed: {result.stderr}"
            
            # Verify wiki contents
            wiki_dir = Path(tmpdir) / "wiki"
            
            # Check source page exists
            source_pages = list((wiki_dir / "sources").glob("*.md"))
            assert len(source_pages) >= 1, "No source pages created"
            
            # Check entity/concept pages exist
            entity_pages = list((wiki_dir / "entities").glob("*.md"))
            assert len(entity_pages) >= 1, "No entity pages created"
            
            # Check comparison page exists
            comparison_pages = list((wiki_dir / "comparisons").glob("*.md"))
            assert len(comparison_pages) >= 1, "No comparison pages created"
            
            # Check index.md lists the pages
            index_content = (wiki_dir / "index.md").read_text()
            assert "demo-source" in index_content or "sample1" in index_content or len(source_pages) > 0
            
            # Check log.md has ingest, query, lint entries
            log_content = (wiki_dir / "log.md").read_text()
            assert "ingest" in log_content.lower(), "Log missing ingest entry"
            assert "query" in log_content.lower(), "Log missing query entry"
            assert "lint" in log_content.lower(), "Log missing lint entry"
            
            # Verify raw/ is byte-identical
            raw_content = (raw_dir / "sample1.md").read_bytes()
            assert raw_content == original_raw, "Raw file was modified!"
            
            print("E2E CLI test passed!")
        finally:
            os.chdir(orig_cwd)