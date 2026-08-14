"""Kommandozeilen-Schnittstelle des Converters.

    python converter.py input.xlsx
    python converter.py input.xlsx --output-dir ./output
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from excelToCsv.errors import ConversionError
from excelToCsv.loggingSetup import addDebugFileHandler, configureLogging
from excelToCsv.pipeline import runConversion

#: Exit-Codes.
EXIT_SUCCESS = 0
EXIT_UNEXPECTED = 1
EXIT_CONVERSION_ERROR = 2


def buildParser() -> argparse.ArgumentParser:
    """Baut den Argument-Parser der CLI."""
    parser = argparse.ArgumentParser(
        prog="converter.py",
        description="Converts an Excel network inventory into Stationen.csv and Netzelemente.csv.",
    )
    parser.add_argument("input", type=Path, help="Path to the input Excel file (.xlsx).")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("."),
        dest="outputDir",
        help="Directory for the generated CSV files (default: current directory).",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        help="Worksheet name or 0-based index. Default: the first worksheet.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Encoding of the CSV output (use utf-8-sig for Excel-friendly BOM).",
    )
    parser.add_argument(
        "--header-row",
        type=int,
        default=None,
        dest="headerRow",
        metavar="N",
        help=(
            "1-based Excel row that holds the column headers. By default the header "
            "row is detected automatically and everything above it is discarded."
        ),
    )
    parser.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "openpyxl", "calamine"],
        help=(
            "Excel reading engine. 'auto' uses the optional, much faster 'calamine' "
            "package when installed and falls back to 'openpyxl'."
        ),
    )
    parser.add_argument(
        "--quote-all",
        action="store_true",
        dest="quoteAll",
        help="Quote every CSV field instead of only the ones that require it.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        dest="logLevel",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Minimum log level for the console (default: INFO).",
    )
    parser.add_argument(
        "--debug-file",
        type=Path,
        default=None,
        dest="debugFile",
        metavar="PATH",
        help=(
            "Write a full DEBUG-level log to this file, in addition to the console. "
            "Always contains full detail regardless of --log-level; plain text, no colors."
        ),
    )
    colorGroup = parser.add_mutually_exclusive_group()
    colorGroup.add_argument(
        "--color",
        action="store_const",
        const=True,
        dest="color",
        default=None,
        help="Force colored log output.",
    )
    colorGroup.add_argument(
        "--no-color",
        action="store_const",
        const=False,
        dest="color",
        help="Disable colored log output.",
    )
    return parser


def resolveSheet(value: str | None) -> str | int | None:
    """Interpretiert ``--sheet`` als Index, wenn es rein numerisch ist."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped.isdigit():
        return int(stripped)
    return stripped


def main(argv: Sequence[str] | None = None) -> int:
    """Einstiegspunkt der CLI. Liefert den Exit-Code zurück."""
    arguments = buildParser().parse_args(argv)
    logger = configureLogging(
        level=getattr(logging, arguments.logLevel),
        color=arguments.color,
    )
    if arguments.debugFile is not None:
        debugPath = addDebugFileHandler(logger, arguments.debugFile)
        logger.info("Writing full debug log to: %s", debugPath)

    try:
        runConversion(
            arguments.input,
            arguments.outputDir,
            logger,
            sheet=resolveSheet(arguments.sheet),
            encoding=arguments.encoding,
            quoteAll=arguments.quoteAll,
            engine=arguments.engine,
            headerRow=arguments.headerRow,
        )
    except ConversionError:
        # Die Ursache wurde bereits detailliert geloggt.
        return EXIT_CONVERSION_ERROR
    except KeyboardInterrupt:  # pragma: no cover - interaktiver Abbruch
        logger.critical("Conversion interrupted by user.")
        return EXIT_UNEXPECTED
    except Exception:
        logger.critical("Unexpected error - conversion aborted.", exc_info=True)
        return EXIT_UNEXPECTED
    return EXIT_SUCCESS
