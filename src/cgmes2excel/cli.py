"""Command line entry point."""

from __future__ import annotations

import argparse
from pathlib import Path

from cgmes2excel.diagnostics import Diagnostics
from cgmes2excel.inputs import InputNotFoundError
from cgmes2excel.logging import configureLogging, getLogger
from cgmes2excel.mapping.elements import NETZELEMENTE_RULES
from cgmes2excel.mapping.rows import RuleDocumentation
from cgmes2excel.mapping.schema import NETZELEMENTE, STATIONEN
from cgmes2excel.mapping.stations import STATIONEN_RULES
from cgmes2excel.pipeline import ConversionOptions, NoDocumentsError, convert

_DEFAULT_OUTPUT = Path("cgmes-export.xlsx")

EXIT_OK = 0
EXIT_SCHEMA_VIOLATION = 1
EXIT_INPUT_ERROR = 2


def buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cgmes2excel",
        description="Convert a CGMES export (EQ/SSH/TP/SV/GL) into the Stationen / NETZELEMENTE workbook.",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="CGMES files, directories or zip archives to convert",
    )
    parser.add_argument("-o", "--output", type=Path, default=_DEFAULT_OUTPUT, help="workbook to write")
    parser.add_argument(
        "--include-class",
        action="append",
        default=[],
        metavar="CIMCLASS",
        help="additionally export this CIM class as a network element (repeatable)",
    )
    parser.add_argument(
        "--only-class",
        action="append",
        default=[],
        metavar="CIMCLASS",
        help="export exactly these CIM classes as network elements (repeatable)",
    )
    parser.add_argument("--log-file", type=Path, help="write an uncoloured log to this file")
    parser.add_argument("--trace-file", type=Path, help="write the derivation of every cell to this file")
    parser.add_argument("-v", "--verbose", action="store_true", help="include DEBUG level detail")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colours")
    parser.add_argument(
        "--print-mapping",
        action="store_true",
        help="print how every output column is derived, then exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = buildParser().parse_args(argv)

    if arguments.print_mapping:
        _printMapping()
        return EXIT_OK

    logger = configureLogging(
        verbose=arguments.verbose,
        colour=False if arguments.no_color else None,
        logFile=arguments.log_file,
    )

    if not arguments.inputs:
        logger.error("No input given. Pass CGMES files, a directory or a zip archive.")
        return EXIT_INPUT_ERROR

    options = ConversionOptions(
        inputs=list(arguments.inputs),
        output=arguments.output,
        includeClasses=list(arguments.include_class),
        onlyClasses=list(arguments.only_class),
        traceFile=arguments.trace_file,
    )

    try:
        result = convert(options)
    except (InputNotFoundError, NoDocumentsError) as exc:
        logger.error("%s", exc)
        return EXIT_INPUT_ERROR

    return EXIT_OK if result.validation.passed else EXIT_SCHEMA_VIOLATION


def _printMapping() -> None:
    print(RuleDocumentation.fromRules(STATIONEN, STATIONEN_RULES).render())
    print()
    print(RuleDocumentation.fromRules(NETZELEMENTE, NETZELEMENTE_RULES).render())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
