"""Orchestration of the conversion.

The fixed order:

    read Excel -> select types -> detect Multipods -> collect stations/elements
    -> ALL validations -> only then write both CSV files.

``convertTable`` is free of I/O and therefore directly testable;
``runConversion`` ties reading, transformation and writing together.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field as dataclassField
from pathlib import Path

import pandas as pd

from excelToCsv.cleanExport import convertCleanTable, prepareCleanCompanions
from excelToCsv.context import ConversionContext, RowSet, subsetRows
from excelToCsv.errors import ConversionError
from excelToCsv.lifecycle import generatedLifecycleDates
from excelToCsv.loggingSetup import findingsLogger
from excelToCsv.maintenance import writeMaintenanceReports
from excelToCsv.mjap import (
    mjapTargetFormat, prepareMjapFrames, prepareCompanions, writeMjapBundle, writeMjapNetwork,
)
from excelToCsv.issues import IssueCollector, ReportedIssue, Issue, SEVERITY_ERROR
from excelToCsv.inputSelection import selectConversionRows
from excelToCsv.multipod import detectMultipodGroups
from excelToCsv.networkElements import (
    NO_STATION_REFERENCE, convertNetworkElements, findElementsWithoutStations,
)
from excelToCsv.reader import (
    DEFAULT_ENGINE,
    InputTable,
    buildInputTable,
    elementTypeColumn,
    textColumn,
)
from excelToCsv.relevance import extractRelevanceColumns
from excelToCsv.schema import (
    COL_ELEMENT_ID,
    DEFAULT_EMPTY_PLACEHOLDER,
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
    validateOutputSchema,
    validateStationReferences,
)
from excelToCsv.targetFormat import loadTargetFormat
from excelToCsv.writer import writeCsvFiles


@dataclass(slots=True)
class ConversionResult:
    """The result of a successful conversion."""

    stations: pd.DataFrame
    networkElements: pd.DataFrame
    sheetName: str
    issues: list[ReportedIssue] = dataclassField(default_factory=list)
    stationsPath: Path | None = None
    networkElementsPath: Path | None = None
    stationSourceRows: list[int] = dataclassField(default_factory=list)
    networkSourceRows: list[int] = dataclassField(default_factory=list)
    sourceElementIds: dict[int, str] = dataclassField(default_factory=dict)
    excludedRows: list[int] = dataclassField(default_factory=list)
    excludedCompanionCount: int = 0
    lifecycleDates: tuple[str, str] | None = None

    @property
    def errorCount(self) -> int:
        return sum(severity == SEVERITY_ERROR for severity, _ in self.issues)

    @property
    def warningCount(self) -> int:
        return len(self.issues) - self.errorCount


def convertTable(
    table: InputTable,
    logger: logging.Logger,
    strict: bool = False,
    *,
    lifecycleDates: tuple[str, str] | None = None,
) -> ConversionResult:
    """Transform a loaded input table into both target record sets.

    Runs every validation. By default errors are logged in full but do NOT stop
    the conversion, so both CSV files are produced and the log is the list of
    things to fix. ``strict=True`` restores the original guarantee: any error
    raises a :class:`~excelToCsv.errors.ConversionError` before anything is
    written.

    Only LINE, TIE, SUB, BUB and DCL enter conversion. Other types are ignored
    before normalization, validation or dependency processing.
    ``lifecycleDates`` generates the same IBN/ABN planning interval for every
    record, bypassing source lifecycle dates.
    """
    table = selectConversionRows(table, logger)
    collector = IssueCollector(logger=logger, strict=strict)
    context = ConversionContext(
        relevanceColumns=extractRelevanceColumns(list(table.frame.columns), logger),
        collector=collector,
        logger=logger,
        lifecycleDates=lifecycleDates,
    )

    elementTypes = elementTypeColumn(table.frame)
    allRows = RowSet(
        frame=table.frame,
        rowNumbers=table.rowNumbers,
        elementIds=textColumn(table.frame, COL_ELEMENT_ID),
        elementTypes=elementTypes,
    )

    stationMask = elementTypes == STATION_TYPE
    stationRows = subsetRows(allRows, stationMask)
    elementRows = subsetRows(allRows, ~stationMask)

    stationIndex = buildStationIndex(stationRows, collector)
    multipods = detectMultipodGroups(elementRows, context, set(stationIndex))
    stations = convertStations(stationRows, context,
                               virtualStationIds={group.nodeId for group in multipods})
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

    networkElements = convertNetworkElements(elementRows, context, stationMjapByElementId,
                                             multipods=multipods)
    validateStationReferences(elementRows, stationIndex, collector)
    validateDuplicateNetworkElements(elementRows, networkElements, collector)

    collector.abortIfFailed("validation")

    validateOutputSchema(stations, STATION_COLUMNS, STATIONS_FILENAME, context)
    validateOutputSchema(networkElements, NETWORK_ELEMENT_COLUMNS, NETWORK_ELEMENTS_FILENAME, context)

    collector.logSummary()

    return ConversionResult(
        stations=stations,
        networkElements=networkElements,
        sheetName=table.sheetName,
        issues=collector.allIssues(),
        stationSourceRows=[int(row) for row in stationRows.rowNumbers],
        networkSourceRows=[int(row) for row in elementRows.rowNumbers],
        sourceElementIds={int(row): elementId for row, elementId in
                          zip(allRows.rowNumbers, allRows.elementIds)},
        lifecycleDates=lifecycleDates,
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
    mjapNetwork: bool = False,
    outagesPath: Path | None = None,
    projectsPath: Path | None = None,
    excludeFindings: bool = False,
    maintenanceReports: bool = False,
) -> ConversionResult:
    """Publish CSVs and, when enabled, automatic maintenance reports.

    The CLI excludes unusable records for MJAP and retains warnings. API callers
    opt in via excludeFindings=True. MJAP always generates lifecycle dates.
    """
    mjapMode = mjap or mjapNetwork
    table = result = None
    findings = []
    published = False
    try:
        targetFormat = loadTargetFormat(targetFormatPath, logger)
        if strict and excludeFindings:
            raise ConversionError('Choose either strict validation or exclusion of elements with findings.')
        if mjap and mjapNetwork:
            raise ConversionError('Choose either the MJAP network export or the four-table bundle.')
        if not mjap and (outagesPath is not None or projectsPath is not None):
            raise ConversionError('--freischaltungen and --projekte require --mjap.')
        if mjapMode:
            targetFormat = mjapTargetFormat(targetFormat)
        table = buildInputTable(inputPath, sheet, logger, engine=engine, headerRow=headerRow,
                                requireLifecycleDates=not mjapMode)
        if excludeFindings:
            result = convertCleanTable(table, logger, mjap=mjapMode)
        else:
            result = convertTable(table, logger, strict=strict or mjapMode,
                                  lifecycleDates=generatedLifecycleDates() if mjapMode else None)
        if result.lifecycleDates is not None:
            logger.info('MJAP planning dates: IBN = %s; ABN = %s for every station and network element. '
                        'Source lifecycle dates are ignored.', *result.lifecycleDates)
        if mjapMode:
            if not excludeFindings and any(issue.problem == NO_STATION_REFERENCE for _, issue in result.issues):
                raise ConversionError('MJAP export cannot discard network elements with missing station references.', issues=result.issues)
            result.stations, result.networkElements = prepareMjapFrames(
                result.stations, result.networkElements, allowEmptyNetwork=mjapNetwork)
        if mjap:
            if excludeFindings:
                outages, projects, companionIssues = prepareCleanCompanions(
                    result.stations, result.networkElements, outagesPath, projectsPath)
                for severity, issue in companionIssues:
                    findingsLogger(logger).error(issue.render('Begleitdatensatz ausgeschlossen.'))
                result.issues += companionIssues
                result.excludedCompanionCount = len({(issue.source, issue.row) for _, issue in companionIssues})
                if outages.empty or projects.empty:
                    raise ConversionError('Nach der Prüfung fehlen gültige Freischaltungen oder Projekte. Das unveränderte MJAP benötigt beide Tabellen mit mindestens einem Datensatz.')
            else:
                outages, projects = prepareCompanions(result.stations, result.networkElements, outagesPath, projectsPath)
            result.stationsPath, result.networkElementsPath = writeMjapBundle(
                targetFormat.applyToStations(result.stations),
                targetFormat.applyToNetworkElements(result.networkElements), outages, projects,
                outputDir, logger, quoteAll=quoteAll,
            )
        elif mjapNetwork:
            result.stationsPath, result.networkElementsPath = writeMjapNetwork(
                targetFormat.applyToStations(result.stations),
                targetFormat.applyToNetworkElements(result.networkElements),
                outputDir, logger, quoteAll=quoteAll,
            )
            if result.networkElements.empty:
                logger.warning(
                    'Keine verbundenen Netzelemente im Export vorhanden. '
                    'Netzelemente.csv wurde mit Spaltenüberschriften geschrieben; '
                    'Stationen.csv enthält %d Station(en). '
                    'Typfilter und Befunde im Pflegebericht prüfen. '
                    'Der vollständige MJAP-Assistent benötigt ein verbundenes Netz.',
                    len(result.stations),
                )
            logger.info(
                'MJAP network export: two CSVs generated from Excel. The complete wizard '
                'also needs nonempty Freischaltungen.csv and Projekte.csv; these were not generated.'
            )
        else:
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
        logger.info(
            "Conversion finished: %d station(s), %d network element(s), "
            "%d error(s), %d warning(s).",
            len(result.stations),
            len(result.networkElements),
            result.errorCount,
            result.warningCount,
        )
        published = True
        return result
    except ConversionError as exc:
        findings = list(exc.issues) or (list(result.issues) if result is not None else [])
        if not exc.issues:
            findings.append((SEVERITY_ERROR, Issue(problem=str(exc),
                action='Ursache in der Eingabe oder Exportkonfiguration beheben und erneut ausführen.')))
        exc.issues = findings
        raise
    except Exception as exc:
        findings = list(result.issues) if result is not None else []
        findings.append((SEVERITY_ERROR, Issue(problem=f'Unerwarteter Exportfehler: {exc}')))
        raise
    finally:
        if maintenanceReports or excludeFindings:
            if published:
                findings = result.issues
            try:
                paths = writeMaintenanceReports(inputPath, outputDir, table, result,
                                                findings, published=published)
                logger.info('Automatische Pflegeberichte: %s; %s', *paths)
            except OSError as exc:
                logger.error('Pflegeberichte konnten nicht geschrieben werden: %s', exc)
                if published:
                    raise ConversionError('CSV-Export veröffentlicht, aber automatische Pflegeberichte konnten nicht geschrieben werden.') from exc
