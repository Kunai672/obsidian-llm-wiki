"""
CLI entry point for llmwiki.
"""
from __future__ import annotations

import sys

from .wiki import init_wiki
from .ingest import cmd_ingest


def cmd_init(args: list[str]) -> int:
    """Initialize the wiki folders and seed files."""
    init_wiki()
    print("Initialized wiki folders and seed files.")
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print("Usage: python -m llmwiki <command> [args...]")
        print("Commands: init, ingest, query, lint, search")
        return 1

    cmd = argv[0]
    args = argv[1:]

    if cmd == "init":
        return cmd_init(args)
    elif cmd == "ingest":
        return cmd_ingest(args)
    else:
        print(f"Unknown command: {cmd}")
        print("Commands: init, ingest, query, lint, search")
        return 1


if __name__ == "__main__":
    sys.exit(main())