#!/usr/bin/env python3
"""arena — CLI entrypoint for the hermes-arena skill.

Thin wrapper that dispatches to arena_cli.main(). Lives next to
arena_cli.py and arena_client.py so they import cleanly.
"""
import os
import sys

# Ensure the script's own directory is importable so `from arena_client import ...`
# inside arena_cli works regardless of the cwd from which `arena` is invoked.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from arena_cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
