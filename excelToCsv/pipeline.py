"""Excel -> ``Stationen.csv`` + ``Netzelemente.csv``.

    read Excel -> keep SUB/LINE/TIE/DCL/BUB rows -> stations (real + virtual)
    -> network elements (lines + tripods) -> MJAP checks -> write CSVs

Any error stops the run before a CSV is written. ``Fehlerliste.csv`` and
``Pflegebericht.html`` are written for every run, so a failed run says what to fix.
"""

from __future__ import annotations

import csv
import logging
from collections import Counter
from dataclasses import dataclass, field as dataclassField
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from excelToCsv.context import ConversionContext
from excelToCsv.elements import convertElements
from excelToCsv.errors import ConversionError
from excelToCsv.issues import EMPTY_DISPLAY, SEVERITY_ERROR, Issue, IssueCollector, ReportedIssue
from excelToCsv.mjap import prepareMjapFrames
from excelToCsv.multipod import findTripods
from excelToCsv.reader import DEFAULT_ENGINE, InputRow, InputTable, buildInputTable
from excelToCsv.relevance import extractRelevanceColumns
from excelToCsv.report import writeReports
from excelToCsv.schema import (
    EXPORTED_TYPES,
    NETWORK_ELEMENT_COLUMNS,
    NETWORK_ELEMENTS_FILENAME,
    STATION_COLUMNS,
    STATION_TYPE,
    STATIONS_FILENAME,
)
from excelToCsv.stations import convertStations

#: End of the planning interval written as ABN.
PLANNING_END = "31.12.2100"


@dataclass(slots=True)
class ConversionResult:
    """Both output tables plus every finding of the run."""

    stations: pd.DataFrame
    networkElements: pd.DataFrame
    sheetName: str
    planningDates: tuple[str, str]
    issues: list[ReportedIssue] = dataclassField(default_factory=list)
    stationsPath: Path | None = None
    networkElementsPath: Path | None = None

    @property
    def errorCount(self) -> int:
        return sum(severity == SEVERITY_ERROR for severity, _ in self.issues)

    @property
    def warningCount(self) -> int:
        return len(self.issues) - self.errorCount


def planningDates() -> tuple[str, str]:
    """IBN = today (Berlin), ABN = 31.12.2100 - the same for every record."""
    return datetime.now(ZoneInfo("Europe/Berlin")).strftime("%d.%m.%Y"), PLANNING_END


def convertTable(table: InputTable, logger: logging.Logger) -> ConversionResult:
    """Build both output tables and collect every finding (no file I/O)."""
    rows = _exportedRows(table, logger)
    context = ConversionContext(
        logger=logger,
        collector=IssueCollector(logger=logger),
        relevanceColumns=extractRelevanceColumns(list(table.frame.columns), logger),
        planningDates=planningDates(),
    )
    stationRows = [row for row in rows if row.elementType == STATION_TYPE]
    lineRows = [row for row in rows if row.elementType != STATION_TYPE]

    tripods, tripodRows = findTripods(lineRows, context.collector)
    stations = convertStations(stationRows, tripods, context)
    elements = convertElements(lineRows, tripods, tripodRows, stations, context)

    context.collector.logSummary()
    return ConversionResult(
        stations=pd.DataFrame(list(stations.values()), columns=list(STATION_COLUMNS), dtype=object),
        networkElements=pd.DataFrame(elements, columns=list(NETWORK_ELEMENT_COLUMNS), dtype=object),
        sheetName=table.sheetName,
        planningDates=context.planningDates,
        issues=context.collector.allIssues(),
    )


def runConversion(
    inputPath: Path,
    outputDir: Path,
    logger: logging.Logger,
    *,
    sheet: str | int | None = None,
    quoteAll: bool = False,
    engine: str = DEFAULT_ENGINE,
    headerRow: int | None = None,
) -> ConversionResult:
    """Read the Excel, convert it, write both CSVs and both reports."""
    table = result = None
    issues: list[ReportedIssue] = []
    try:
        table = buildInputTable(inputPath, sheet, logger, engine=engine, headerRow=headerRow)
        result = convertTable(table, logger)
        issues = result.issues
        if result.errorCount:
            raise ConversionError(f"{result.errorCount} error(s) in the input - no CSV written.",
                                  issues=issues)
        result.stations, result.networkElements = prepareMjapFrames(result.stations,
                                                                    result.networkElements)
        outputDir = Path(outputDir)
        quoting = csv.QUOTE_ALL if quoteAll else csv.QUOTE_MINIMAL
        result.stationsPath = _writeCsv(result.stations, outputDir / STATIONS_FILENAME,
                                        quoting, logger)
        result.networkElementsPath = _writeCsv(result.networkElements,
                                               outputDir / NETWORK_ELEMENTS_FILENAME, quoting, logger)
        logger.info("Conversion finished: %d station(s), %d network element(s), %d warning(s).",
                    len(result.stations), len(result.networkElements), result.warningCount)
        return result
    except ConversionError as error:
        if not error.issues:
            error.issues = [(SEVERITY_ERROR, Issue(
                problem=str(error),
                action="Ursache in der Eingabe beheben und erneut ausführen."))]
        issues = error.issues
        raise
    except Exception as error:
        issues = [*issues, (SEVERITY_ERROR, Issue(problem=f"Unerwarteter Exportfehler: {error}"))]
        raise
    finally:
        try:
            logger.info("Pflegeberichte: %s; %s",
                        *writeReports(inputPath, outputDir, table, result, issues))
        except OSError as error:
            logger.error("Pflegeberichte konnten nicht geschrieben werden: %s", error)


def _exportedRows(table: InputTable, logger: logging.Logger) -> list[InputRow]:
    """Rows of the exported types; other types are ignored and counted in the log."""
    rows, ignored = [], Counter()
    for row in table.rows():
        if row.elementType in EXPORTED_TYPES:
            rows.append(row)
        else:
            ignored[row.elementType or EMPTY_DISPLAY] += 1
    if ignored:
        logger.info("Ignoring %d row(s) of other types: %s.", sum(ignored.values()),
                    ", ".join(f"{kind}: {count}" for kind, count in sorted(ignored.items())))
    return rows


def _writeCsv(frame: pd.DataFrame, path: Path, quoting: int, logger: logging.Logger) -> Path:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False, encoding="utf-8-sig", quoting=quoting, lineterminator="\n")
    except OSError as error:
        raise ConversionError(f"Cannot write {path}: {error}") from error
    logger.info("Created %s (%d record(s)).", path.name, len(frame))
    return path
