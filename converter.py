#!/usr/bin/env python3
"""CLI entry point: ``python converter.py input.xlsx [--output-dir ./output]``."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from excelToCsv.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
