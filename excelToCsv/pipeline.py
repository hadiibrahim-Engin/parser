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
from excelToCsv.inputSelection import selectConversionRows
from excelToCsv.multipod import detectMultipodGroups
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
)
from excelToCsv.stations import convertStations
from excelToCsv.validate import (
    buildStationIndex,
    validateDuplicateNetworkElements,
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
    stationSourceRows: list[int] = dataclassField(default_factory=list)
    networkSourceRows: list[int] = dataclassField(default_factory=list)
    sourceElementIds: dict[int, str] = dataclassField(default_factory=dict)
    excludedRows: list[int] = dataclassField(default_factory=list)
    excludedCompanionCount: int = 0


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

    Only LINE, TIE, SUB, BUB and DCL enter conversion. Other types are ignored
    before normalization, validation or dependency processing.
    """
    table = selectConversionRows(table, logger)
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
        warningCount=len(collector.warnings),
        errorCount=len(collector.errors),
        issues=collector.allIssues(),
        stationSourceRows=[int(row) for row in stationRows.rowNumbers],
        networkSourceRows=[int(row) for row in elementRows.rowNumbers],
        sourceElementIds={int(row): elementId for row, elementId in
                          zip(table.rowNumbers, textColumn(table.frame, COL_ELEMENT_ID))},
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

    The CLI enables exclusion/reporting for MJAP. API callers opt in via
    excludeFindings=True; the historical API defaults stay compatible.
    """
    from excelToCsv.errors import ConversionError
    from excelToCsv.issues import Issue, SEVERITY_ERROR
    from excelToCsv.maintenance import writeMaintenanceReports
    audit = {}
    options = dict(sheet=sheet, encoding=encoding, quoteAll=quoteAll, engine=engine,
                   headerRow=headerRow, strict=strict, emptyPlaceholder=emptyPlaceholder,
                   targetFormatPath=targetFormatPath, mjap=mjap, mjapNetwork=mjapNetwork,
                   outagesPath=outagesPath, projectsPath=projectsPath,
                   excludeFindings=excludeFindings, audit=audit)
    published = False
    findings = []
    try:
        result = _runConversion(inputPath, outputDir, logger, **options)
        findings = result.issues
        published = True
        return result
    except ConversionError as exc:
        findings = list(exc.issues) or list(audit['result'].issues if 'result' in audit else [])
        if not exc.issues:
            findings.append((SEVERITY_ERROR, Issue(problem=str(exc),
                action='Ursache in der Eingabe oder Exportkonfiguration beheben und erneut ausführen.')))
        exc.issues = findings
        raise
    except Exception as exc:
        findings = list(audit['result'].issues if 'result' in audit else [])
        findings.append((SEVERITY_ERROR, Issue(problem=f'Unerwarteter Exportfehler: {exc}')))
        raise
    finally:
        if maintenanceReports or excludeFindings:
            try:
                paths = writeMaintenanceReports(inputPath, outputDir, audit.get('table'),
                    audit.get('result'), findings, published=published)
                logger.info('Automatische Pflegeberichte: %s; %s', *paths)
            except OSError as exc:
                logger.error('Pflegeberichte konnten nicht geschrieben werden: %s', exc)
                if published:
                    raise ConversionError('CSV-Export veröffentlicht, aber automatische Pflegeberichte konnten nicht geschrieben werden.') from exc


def _runConversion(
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
    audit: dict | None = None,
) -> ConversionResult:
    """Read Excel and publish the selected CSV format.

    The Python API retains its historical default. The CLI explicitly selects
    ``mjapNetwork=True`` for the safe, two-table network export; ``mjap=True``
    selects the complete four-table bundle with genuine companion inputs.
    """
    targetFormat = loadTargetFormat(targetFormatPath, logger)
    if strict and excludeFindings:
        from excelToCsv.errors import ConversionError
        raise ConversionError('Choose either strict validation or exclusion of elements with findings.')
    if mjap and mjapNetwork:
        from excelToCsv.errors import ConversionError
        raise ConversionError('Choose either the MJAP network export or the four-table bundle.')
    if not mjap and (outagesPath is not None or projectsPath is not None):
        from excelToCsv.errors import ConversionError
        raise ConversionError('--freischaltungen and --projekte require --mjap.')
    if mjap or mjapNetwork:
        from excelToCsv.mjap import (mjapTargetFormat, prepareMjapFrames, prepareCompanions,
                                    writeMjapBundle, writeMjapNetwork)
        targetFormat = mjapTargetFormat(targetFormat)
    table = buildInputTable(inputPath, sheet, logger, engine=engine, headerRow=headerRow)
    table = selectConversionRows(table, logger)
    if audit is not None:
        audit['table'] = table
    if excludeFindings:
        from excelToCsv.cleanExport import convertCleanTable
        result = convertCleanTable(table, logger, mjap=mjap or mjapNetwork)
    else:
        result = convertTable(table, logger, strict=strict or mjap or mjapNetwork)
    if audit is not None:
        audit['result'] = result
    if strict and (mjap or mjapNetwork) and result.warningCount:
        from excelToCsv.errors import ConversionError
        raise ConversionError('Strikter MJAP-Export abgebrochen: Warnungen müssen zuerst gepflegt werden.', issues=result.issues)
    if mjap or mjapNetwork:
        if not excludeFindings and any(issue.problem == 'Network element has no usable station reference.' for _, issue in result.issues):
            from excelToCsv.errors import ConversionError
            raise ConversionError('MJAP export cannot discard network elements with missing station references.', issues=result.issues)
        result.stations, result.networkElements = prepareMjapFrames(result.stations, result.networkElements)
        if mjap:
            if excludeFindings:
                from excelToCsv.cleanExport import prepareCleanCompanions
                from excelToCsv.loggingSetup import findingsLogger
                outages, projects, companionIssues = prepareCleanCompanions(
                    result.stations, result.networkElements, outagesPath, projectsPath)
                for severity, issue in companionIssues:
                    findingsLogger(logger).error(issue.render('Begleitdatensatz ausgeschlossen.'))
                result.issues += companionIssues
                result.errorCount += len(companionIssues)
                result.excludedCompanionCount = len({(issue.source, issue.row) for _, issue in companionIssues})
                if outages.empty or projects.empty:
                    from excelToCsv.errors import ConversionError
                    raise ConversionError('Nach der Prüfung fehlen gültige Freischaltungen oder Projekte. Das unveränderte MJAP benötigt beide Tabellen mit mindestens einem Datensatz.')
            else:
                outages, projects = prepareCompanions(result.stations, result.networkElements, outagesPath, projectsPath)
    if mjap:
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
    return result
