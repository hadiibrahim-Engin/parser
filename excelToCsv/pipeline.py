"""Orchestration of the conversion.

The fixed order:

    read Excel -> normalize -> collect stations -> collect network elements
    -> ALL validations -> only then write both CSV files.

``convertTable`` is free of I/O and therefore directly testable;
``runConversion`` ties reading, transformation and writing together.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from excelToCsv.context import ConversionContext, RowSet, subsetRows
from excelToCsv.issues import IssueCollector
from excelToCsv.networkElements import convertNetworkElements
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
    NETWORK_ELEMENT_COLUMNS,
    NETWORK_ELEMENTS_FILENAME,
    STATION_COLUMNS,
    STATION_TYPE,
    STATIONS_FILENAME,
)
from excelToCsv.stations import convertStations
from excelToCsv.validate import (
    buildStationIndex,
    validateDuplicateNetworkElements,
    validateElementTypes,
    validateOutputSchema,
    validateStationReferences,
)
from excelToCsv.writer import writeCsvFiles


@dataclass(slots=True)
class ConversionResult:
    """The result of a successful conversion."""

    stations: pd.DataFrame
    networkElements: pd.DataFrame
    sheetName: str
    warningCount: int
    stationsPath: Path | None = None
    networkElementsPath: Path | None = None


def convertTable(table: InputTable, logger: logging.Logger) -> ConversionResult:
    """Transform a loaded input table into both target record sets.

    Runs every validation and raises a
    :class:`~excelToCsv.errors.ConversionError` on fatal findings, before
    anything could be written.
    """
    collector = IssueCollector(logger=logger)
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

    stationMask = elementTypes == STATION_TYPE
    stationRows = subsetRows(allRows, stationMask)
    elementRows = subsetRows(allRows, ~stationMask)

    stations = convertStations(stationRows, context)
    stationIndex = buildStationIndex(stationRows, collector)

    networkElements = convertNetworkElements(elementRows, context)
    validateStationReferences(elementRows, stationIndex, collector)
    validateDuplicateNetworkElements(elementRows, networkElements, collector)

    collector.abortIfFailed("validation")

    validateOutputSchema(stations, STATION_COLUMNS, STATIONS_FILENAME, context)
    validateOutputSchema(networkElements, NETWORK_ELEMENT_COLUMNS, NETWORK_ELEMENTS_FILENAME, context)

    if collector.warnings:
        logger.info("Validation successful with %d warning(s).", len(collector.warnings))
    else:
        logger.info("Validation successful.")

    return ConversionResult(
        stations=stations,
        networkElements=networkElements,
        sheetName=table.sheetName,
        warningCount=len(collector.warnings),
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
) -> ConversionResult:
    """Full run: read Excel, convert, validate, write the CSV files."""
    table = buildInputTable(inputPath, sheet, logger, engine=engine, headerRow=headerRow)
    result = convertTable(table, logger)
    result.stationsPath, result.networkElementsPath = writeCsvFiles(
        result.stations,
        result.networkElements,
        outputDir,
        logger,
        encoding=encoding,
        quoteAll=quoteAll,
    )
    logger.info(
        "Conversion finished successfully: %d station(s), %d network element(s), %d warning(s).",
        len(result.stations),
        len(result.networkElements),
        result.warningCount,
    )
    return result
