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
EXIT_PARTIAL_EXPORT = 3


def buildParser() -> argparse.ArgumentParser:
    """Read export options; the default writes the two MJAP network CSVs."""
    parser = argparse.ArgumentParser(prog='converter.py',
        description='Convert Excel into MJAP-compatible Stationen.csv and Netzelemente.csv.')
    parser.add_argument('input', type=Path, help='Input Excel file (.xlsx).')
    parser.add_argument('-o', '--output-dir', type=Path, default=Path('.'), dest='outputDir',
                        help='Output directory (default: current directory).')
    parser.add_argument('--sheet', help='Worksheet name or 0-based index (default: first sheet).')
    parser.add_argument('--header-row', type=int, dest='headerRow', metavar='N',
                        help='1-based header row (default: automatic detection).')
    parser.add_argument('--engine', default='auto', choices=['auto', 'openpyxl', 'calamine'],
                        help='Excel reader (auto prefers calamine if installed).')

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--mjap', action='store_true', help='Export all four MJAP tables.')
    mode.add_argument('--legacy', action='store_true', help='Use the historical CSV format.')
    parser.add_argument('--freischaltungen', type=Path, dest='outagesPath',
                        help='Switching CSV with real records; required for --mjap.')
    parser.add_argument('--projekte', type=Path, dest='projectsPath',
                        help='Project CSV with real records; required for --mjap.')
    parser.add_argument('--strict', action='store_true', help='Abort on errors; retain warnings.')
    parser.add_argument('--quote-all', action='store_true', dest='quoteAll', help='Quote every CSV field.')
    parser.add_argument('--target-format', type=Path, dest='targetFormatPath', metavar='FILE',
                        help='JSON column/type mapping; MJAP requires canonical column names.')
    parser.add_argument('--encoding', default='utf-8', help='Legacy encoding; MJAP always uses UTF-8 with BOM.')
    parser.add_argument('--empty-placeholder', default=DEFAULT_EMPTY_PLACEHOLDER, dest='emptyPlaceholder',
                        metavar='TEXT', help='Legacy filler for empty columns (default: one space).')

    parser.add_argument('--details', action='store_true', dest='showDetails', help='Print every finding.')
    parser.add_argument('--log-level', default='INFO', dest='logLevel',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
    parser.add_argument('--issue-file', type=Path, dest='issueFile', metavar='PATH',
                        help='Additional findings report (.csv or text), including failed runs.')
    parser.add_argument('--debug-file', type=Path, dest='debugFile', metavar='PATH',
                        help='Full DEBUG log, independent of console log level.')
    color = parser.add_mutually_exclusive_group()
    color.add_argument('--color', action='store_const', const=True, dest='color', default=None,
                       help='Force colored logs.')
    color.add_argument('--no-color', action='store_const', const=False, dest='color', help='Disable colored logs.')
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
            mjapNetwork=not arguments.mjap and not arguments.legacy,
            outagesPath=arguments.outagesPath,
            projectsPath=arguments.projectsPath,
            excludeFindings=not arguments.legacy and not arguments.strict,
            maintenanceReports=True,
        )
    except ConversionError as exc:
        # The cause has already been logged in full detail. The report matters
        # most for exactly this run, so it is written before returning.
        logger.error("Export aborted: %s", exc)
        writeReport(arguments.issueFile, failureIssues(exc), logger)
        return EXIT_CONVERSION_ERROR
    except KeyboardInterrupt:  # pragma: no cover - interactive abort
        logger.critical("Conversion interrupted by user.")
        return EXIT_UNEXPECTED
    except Exception:
        logger.critical("Unexpected error - conversion aborted.", exc_info=True)
        return EXIT_UNEXPECTED

    writeReport(arguments.issueFile, result.issues, logger)
    # A published partial dataset has a distinct status from a failed export.
    if result.excludedRows or result.excludedCompanionCount:
        logger.warning('Teil-Export veröffentlicht. Ausgeschlossene Elemente stehen in Fehlerliste.csv und Pflegebericht.html. Exit-Code: 3.')
        return EXIT_PARTIAL_EXPORT
    return EXIT_CONVERSION_ERROR if result.errorCount else EXIT_SUCCESS
