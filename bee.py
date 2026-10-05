#!/usr/bin/env python
"""BEE launcher — run:  python bee.py [repl|voice|web|plan|speak|eval|setup]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bee.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
