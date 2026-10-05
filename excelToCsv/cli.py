"""Command line interface of the converter.

    python converter.py input.xlsx
    python converter.py input.xlsx --output-dir ./output
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from excelToCsv.errors import ConversionError
from excelToCsv.issues import (
    SEVERITY_ERROR,
    Issue,
    ReportedIssue,
    writeIssueReport,
)
from excelToCsv.loggingSetup import addDebugFileHandler, configureLogging
from excelToCsv.pipeline import runConversion
from excelToCsv.schema import DEFAULT_EMPTY_PLACEHOLDER

#: Exit codes.
EXIT_SUCCESS = 0
EXIT_UNEXPECTED = 1
EXIT_CONVERSION_ERROR = 2


def buildParser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="converter.py",
        description="Converts an Excel network inventory into Stationen.csv and Netzelemente.csv.",
    )
    parser.add_argument("input", type=Path, help="Path to the input Excel file (.xlsx).")
    parser.add_argument('--mjap', action='store_true',
                        help='Write an MJAP-compatible four-table bundle; validate strictly.')
    parser.add_argument('--freischaltungen', type=Path, dest='outagesPath',
                        help='Existing switching CSV for --mjap; otherwise emit an empty table.')
    parser.add_argument('--projekte', type=Path, dest='projectsPath',
                        help='Existing project CSV for --mjap; otherwise emit an empty table.')
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
        "--target-format",
        type=Path,
        default=None,
        dest="targetFormatPath",
        metavar="FILE",
        help=(
            "JSON file renaming output columns and translating ELEMENT-TYPE values "
            "(e.g. LINE -> Stromkreis). Affects the target format only; input column "
            "names stay untouched. See targetFormat.example.json."
        ),
    )
    parser.add_argument(
        "--empty-placeholder",
        default=DEFAULT_EMPTY_PLACEHOLDER,
        dest="emptyPlaceholder",
        metavar="TEXT",
        help=(
            "Filler for columns that are empty in every row (default: a single space). "
            "Without it pandas types such a column as numeric NaN and the .str accessor "
            "fails downstream. Pass '' to keep those columns truly empty."
        ),
    )
    parser.add_argument(
        "--details",
        action="store_true",
        dest="showDetails",
        help=(
            "Print every single finding on the console instead of only the grouped "
            "summary. The details always reach --issue-file and --debug-file regardless."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Abort on the first phase that produced an error and write no CSV file at all. "
            "By default errors are logged but both CSV files are still produced."
        ),
    )
    parser.add_argument(
        "--issue-file",
        type=Path,
        default=None,
        dest="issueFile",
        metavar="PATH",
        help=(
            "Write every error and warning of the run to this file, sorted by Excel row, "
            "so they can be worked through. A '.csv' target opens straight in Excel next "
            "to the input; any other suffix gets the same readable blocks as the console. "
            "Written even when the conversion aborts."
        ),
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
    """Interpret ``--sheet`` as an index when it is purely numeric."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped.isdigit():
        return int(stripped)
    return stripped


def failureIssues(error: ConversionError) -> list[ReportedIssue]:
    """Findings to report for a failed run.

    Validation failures carry their structured findings. Failures raised outside
    the collector - a missing input column, an unreadable file - carry none, so
    the message itself becomes the single reported entry rather than leaving the
    user with an empty report.
    """
    if error.issues:
        return list(error.issues)  # type: ignore[arg-type]
    return [(SEVERITY_ERROR, Issue(problem=str(error)))]


def writeReport(
    path: Path | None,
    issues: list[ReportedIssue],
    logger: logging.Logger,
) -> None:
    """Write the issue report when one was requested; never break the run over it."""
    if path is None:
        return
    try:
        writeIssueReport(issues, path, logger)
    except OSError as exc:
        logger.error("Could not write the issue report to %s: %s", path, exc)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the exit code."""
    arguments = buildParser().parse_args(argv)
    logger = configureLogging(
        level=getattr(logging, arguments.logLevel),
        color=arguments.color,
        showDetails=arguments.showDetails,
    )
    if arguments.debugFile is not None:
        debugPath = addDebugFileHandler(logger, arguments.debugFile)
        logger.info("Writing full debug log to: %s", debugPath)

    try:
        result = runConversion(
            arguments.input,
            arguments.outputDir,
            logger,
            sheet=resolveSheet(arguments.sheet),
            encoding=arguments.encoding,
            quoteAll=arguments.quoteAll,
            engine=arguments.engine,
            headerRow=arguments.headerRow,
            strict=arguments.strict,
            emptyPlaceholder=arguments.emptyPlaceholder,
            targetFormatPath=arguments.targetFormatPath,
            mjap=arguments.mjap,
            outagesPath=arguments.outagesPath,
            projectsPath=arguments.projectsPath,
        )
    except ConversionError as exc:
        # The cause has already been logged in full detail. The report matters
        # most for exactly this run, so it is written before returning.
        writeReport(arguments.issueFile, failureIssues(exc), logger)
        return EXIT_CONVERSION_ERROR
    except KeyboardInterrupt:  # pragma: no cover - interactive abort
        logger.critical("Conversion interrupted by user.")
        return EXIT_UNEXPECTED
    except Exception:
        logger.critical("Unexpected error - conversion aborted.", exc_info=True)
        return EXIT_UNEXPECTED

    writeReport(arguments.issueFile, result.issues, logger)
    # The files exist either way; the exit code still reports that the run had
    # errors, so automation does not mistake a flawed run for a clean one.
    return EXIT_CONVERSION_ERROR if result.errorCount else EXIT_SUCCESS
