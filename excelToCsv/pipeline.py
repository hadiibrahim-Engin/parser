"""Orchestration of the conversion.

The fixed order:

    read Excel -> normalize -> collect stations -> collect network elements
    -> ALL validations -> only then write both CSV files.

``convertTable`` is free of I/O and therefore directly testable;
``runConversion`` ties reading, transformation and writing together.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field as dataclassField
from pathlib import Path

import numpy as np
import pandas as pd

from excelToCsv.context import ConversionContext, RowSet, subsetRows
from excelToCsv.issues import IssueCollector, ReportedIssue
from excelToCsv.networkElements import convertNetworkElements, findElementsWithoutStations
from excelToCsv.normalize import normalizeElementType
from excelToCsv.reader import (
    DEFAULT_ENGINE,
    InputTable,
    buildInputTable,
    columnValues,
    textColumn,
)
from excelToCsv.relevance import extractRelevanceColumns
from excelToCsv.schema import (
    COL_ELEMENT_ID,
    COL_ELEMENT_TYPE,
    DEFAULT_EMPTY_PLACEHOLDER,
    NETWORK_ELEMENT_COLUMNS,
    NETWORK_ELEMENTS_FILENAME,
    STATION_COLUMNS,
    STATION_TYPE,
    STATIONS_FILENAME,
    VALID_ELEMENT_TYPES,
)
from excelToCsv.stations import convertStations
from excelToCsv.validate import (
    buildStationIndex,
    validateDuplicateNetworkElements,
    validateElementTypes,
    validateMultipodReferences,
    validateOutputSchema,
    validateStationReferences,
)
from excelToCsv.targetFormat import TargetFormat, loadTargetFormat
from excelToCsv.writer import writeCsvFiles


@dataclass(slots=True)
class ConversionResult:
    """The result of a successful conversion."""

    stations: pd.DataFrame
    networkElements: pd.DataFrame
    sheetName: str
    warningCount: int
    errorCount: int = 0
    issues: list[ReportedIssue] = dataclassField(default_factory=list)
    stationsPath: Path | None = None
    networkElementsPath: Path | None = None


def convertTable(
    table: InputTable,
    logger: logging.Logger,
    strict: bool = False,
) -> ConversionResult:
    """Transform a loaded input table into both target record sets.

    Runs every validation. By default errors are logged in full but do NOT stop
    the conversion, so both CSV files are produced and the log is the list of
    things to fix. ``strict=True`` restores the original guarantee: any error
    raises a :class:`~excelToCsv.errors.ConversionError` before anything is
    written.

    Rows whose ``ELEMENT-TYPE`` is unknown are the one exception: they cannot be
    routed to either file, so in lenient mode they are dropped and reported
    instead of being written with a bogus type.
    """
    collector = IssueCollector(logger=logger, strict=strict)
    context = ConversionContext(
        relevanceColumns=extractRelevanceColumns(list(table.frame.columns), logger),
        collector=collector,
        logger=logger,
    )

    elementTypes = np.fromiter(
        (normalizeElementType(value) for value in columnValues(table.frame, COL_ELEMENT_TYPE)),
        dtype=object,
        count=len(table.frame),
    )
    allRows = RowSet(
        frame=table.frame,
        rowNumbers=table.rowNumbers,
        elementIds=textColumn(table.frame, COL_ELEMENT_ID),
        elementTypes=elementTypes,
    )

    validateElementTypes(elementTypes, allRows, collector)
    collector.abortIfFailed("element type classification")

    classifiable = np.fromiter(
        (elementType in VALID_ELEMENT_TYPES for elementType in elementTypes),
        dtype=bool,
        count=len(elementTypes),
    )
    if not classifiable.all():
        logger.warning(
            "Skipping %d row(s) with an unknown ELEMENT-TYPE - they cannot be routed "
            "to either output file. See the errors above for the affected rows.",
            int((~classifiable).sum()),
        )
        allRows = subsetRows(allRows, classifiable)
        elementTypes = elementTypes[classifiable]

    stationMask = elementTypes == STATION_TYPE
    stationRows = subsetRows(allRows, stationMask)
    elementRows = subsetRows(allRows, ~stationMask)

    stations = convertStations(stationRows, context)
    stationIndex = buildStationIndex(stationRows, collector)
    stationMjapByElementId = dict(
        zip(stationRows.elementIds, stations["MJAP-ID"].to_numpy(dtype=object), strict=True)
    )

    # Elements without a usable station reference cannot be placed in the grid.
    # They are reported and removed here, so the validations below and the output
    # operate on exactly the same set of rows.
    usable = findElementsWithoutStations(elementRows, context)
    if not usable.all():
        logger.warning(
            "Removing %d network element(s) without a usable station reference from the "
            "output. They are listed in the issue report.",
            int((~usable).sum()),
        )
        elementRows = subsetRows(elementRows, usable)

    networkElements = convertNetworkElements(elementRows, context, stationMjapByElementId)
    validateStationReferences(elementRows, stationIndex, collector)
    validateMultipodReferences(elementRows, stationIndex, collector)
    validateDuplicateNetworkElements(elementRows, networkElements, collector)

    collector.abortIfFailed("validation")

    validateOutputSchema(stations, STATION_COLUMNS, STATIONS_FILENAME, context)
    validateOutputSchema(networkElements, NETWORK_ELEMENT_COLUMNS, NETWORK_ELEMENTS_FILENAME, context)

    collector.logSummary()

    return ConversionResult(
        stations=stations,
        networkElements=networkElements,
        sheetName=table.sheetName,
        warningCount=len(collector.warnings),
        errorCount=len(collector.errors),
        issues=collector.allIssues(),
    )


def runConversion(
    inputPath: Path,
    outputDir: Path,
    logger: logging.Logger,
    *,
    sheet: str | int | None = None,
    encoding: str = "utf-8",
    quoteAll: bool = False,
    engine: str = DEFAULT_ENGINE,
    headerRow: int | None = None,
    strict: bool = False,
    emptyPlaceholder: str = DEFAULT_EMPTY_PLACEHOLDER,
    targetFormatPath: Path | None = None,
    mjap: bool = False,
    outagesPath: Path | None = None,
    projectsPath: Path | None = None,
) -> ConversionResult:
    """Full run: read Excel, convert, validate, write the CSV files."""
    targetFormat = loadTargetFormat(targetFormatPath, logger)
    if not mjap and (outagesPath is not None or projectsPath is not None):
        from excelToCsv.errors import ConversionError
        raise ConversionError('--freischaltungen and --projekte require --mjap.')
    if mjap:
        from excelToCsv.mjap import mjapTargetFormat, prepareMjapFrames, prepareCompanions, writeCompanions
        targetFormat = mjapTargetFormat(targetFormat)
    table = buildInputTable(inputPath, sheet, logger, engine=engine, headerRow=headerRow)
    result = convertTable(table, logger, strict=strict or mjap)
    if mjap:
        result.stations, result.networkElements = prepareMjapFrames(result.stations, result.networkElements)
        outages, projects = prepareCompanions(result.stations, result.networkElements, outagesPath, projectsPath)
        # Optional topology values must become NA; only the paired date columns
        # use a text sentinel because the unchanged plugin calls .str on them.
        emptyPlaceholder = ''
        encoding = 'utf-8-sig'
    result.stationsPath, result.networkElementsPath = writeCsvFiles(
        result.stations,
        result.networkElements,
        outputDir,
        logger,
        encoding=encoding,
        quoteAll=quoteAll,
        emptyPlaceholder=emptyPlaceholder,
        targetFormat=targetFormat,
    )
    if mjap:
        writeCompanions(outages, projects, outputDir, logger)
    logger.info(
        "Conversion finished: %d station(s), %d network element(s), "
        "%d error(s), %d warning(s).",
        len(result.stations),
        len(result.networkElements),
        result.errorCount,
        result.warningCount,
    )
    return result
