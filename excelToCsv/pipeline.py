"""Orchestrierung der Conversion.

Fester Ablauf:

    Excel lesen -> normalisieren -> Stationen erfassen -> Netzelemente erfassen
    -> ALLE Validierungen -> erst dann beide CSV-Dateien schreiben.

``convertTable`` ist frei von I/O und dadurch direkt testbar;
``runConversion`` verbindet Lesen, Transformation und Schreiben.
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
    """Ergebnis einer erfolgreichen Conversion."""

    stations: pd.DataFrame
    networkElements: pd.DataFrame
    sheetName: str
    warningCount: int
    stationsPath: Path | None = None
    networkElementsPath: Path | None = None


def convertTable(table: InputTable, logger: logging.Logger) -> ConversionResult:
    """Transformiert eine eingelesene Inputtabelle in beide Zieldatensätze.

    Führt sämtliche Validierungen durch und wirft bei fatalen Befunden einen
    :class:`~excelToCsv.errors.ConversionError`, bevor irgendetwas geschrieben
    werden kann.
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
) -> ConversionResult:
    """Vollständiger Lauf: Excel lesen, konvertieren, validieren, CSVs schreiben."""
    table = buildInputTable(inputPath, sheet, logger, engine=engine)
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
