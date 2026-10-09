"""Export only Excel elements without findings, including dependency closure."""
from __future__ import annotations

from dataclasses import replace
from collections import defaultdict
from typing import TYPE_CHECKING

import pandas as pd

from excelToCsv.errors import ConversionError
from excelToCsv.issues import Issue, ReportedIssue, SEVERITY_ERROR, sortIssues
from excelToCsv.inputSelection import selectConversionRows
from excelToCsv.normalize import normalizeElementType
from excelToCsv.reader import InputTable, textColumn

if TYPE_CHECKING:
    from excelToCsv.pipeline import ConversionResult


def validateMjapRecords(result: ConversionResult) -> list[ReportedIssue]:
    """Attach MJAP-only defects to actual source rows before publication.

    The final shared prepareMjapFrames validator remains the publication guard.
    This pass provides per-element context so a local defect can be quarantined.
    """
    from excelToCsv.mjap import _validateShapeId
    findings: list[ReportedIssue] = []

    def error(frame, position, source, kind, field, problem, value=None):
        findings.append((SEVERITY_ERROR, Issue(
            problem=problem, row=int(source[position]),
            elementId=result.sourceElementIds[int(source[position])],
            elementType=kind, field=field, value=value,
            expected="Gültiger MJAP-Datensatz mit eindeutiger ID, gültigem IBN und vorhandenen Anschlüssen.",
        )))

    for frame, source, kind in (
        (result.stations, result.stationSourceRows, 'SUB'),
        (result.networkElements, result.networkSourceRows, ''),
    ):
        starts = pd.to_datetime(frame['IBN'], format='%d.%m.%Y', errors='coerce')
        ends = pd.to_datetime(frame['ABN'], format='%d.%m.%Y', errors='coerce')
        duplicates = frame['MJAP-ID'].duplicated(keep=False)
        for position, (_, record) in enumerate(frame.iterrows()):
            recordType = kind or record['Element Typ']
            try:
                _validateShapeId(record['MJAP-ID'])
            except ConversionError as exc:
                error(frame, position, source, recordType, 'MJAP-ID', str(exc), record['MJAP-ID'])
            start, end = starts.iloc[position], ends.iloc[position]
            if pd.isna(start):
                error(frame, position, source, recordType, 'STARTLIFETIME',
                      'MJAP benötigt ein gültiges IBN-Datum; ein fehlendes Datum wird nicht erfunden.', record['IBN'])
            elif pd.notna(end) and start > end:
                error(frame, position, source, recordType, 'STARTLIFETIME / ENDLIFETIME',
                      'IBN liegt nach ABN.', f"{record['IBN']} / {record['ABN']}")
            if str(record['ABN']).strip() and pd.isna(end):
                error(frame, position, source, recordType, 'ENDLIFETIME',
                      'Der geprüfte MJAP-Export benötigt ein einzelnes gültiges ABN-Datum oder einen leeren Wert.', record['ABN'])
        for position in range(len(frame)):
            if duplicates.iloc[position]:
                record = frame.iloc[position]
                error(frame, position, source, kind or record['Element Typ'], 'MJAP-ID',
                      'Doppelte MJAP-ID.', record['MJAP-ID'])

    stations = result.stations
    ids = set(stations['MJAP-ID'])
    coordinates = {}
    numericCoordinates = stations[['lat', 'long']].apply(pd.to_numeric, errors='coerce')
    for position, (_, record) in enumerate(stations.iterrows()):
        pair = numericCoordinates.iloc[position]
        if pair.isna().any() or not all(float('-inf') < value < float('inf') for value in pair):
            error(stations, position, result.stationSourceRows, 'SUB', 'Latitude / Longitude',
                  'MJAP benötigt endliche numerische Koordinaten.', f"{record['lat']} / {record['long']}")
        else:
            coordinates[record['MJAP-ID']] = tuple(pair)

    shapeOwners = defaultdict(list)
    elements = result.networkElements
    for position, (_, record) in enumerate(elements.iterrows()):
        start, end = record['Station Anfang:MJAP-ID'], record['Station Ende:MJAP-ID']
        third, node = record['Station T-1:MJAP-ID'], record['Y-Knoten-1: MJAP-ID']
        edges = [(station, node) for station in (start, end, third)] if third else [(start, end)]
        for first, second in ([(start, end), *edges] if third else edges):
            if first not in ids or second not in ids:
                error(elements, position, result.networkSourceRows, record['Element Typ'],
                      'Station 1 / Station 2 / Multipod', 'Anschlussstation fehlt im MJAP-Netz.', f'{first} / {second}')
            elif first == second or (first in coordinates and second in coordinates
                                      and coordinates[first] == coordinates[second]):
                error(elements, position, result.networkSourceRows, record['Element Typ'],
                      'Station 1 / Station 2 / Multipod', 'Leitung mit identischen Endpunkten oder Koordinaten.', f'{first} / {second}')
        generated = [f"{record['MJAP-ID']}_Y{number}" for number in (1, 2, 3)] if third else [record['MJAP-ID']]
        for identifier in generated:
            shapeOwners[identifier].append(position)
            try:
                _validateShapeId(identifier)
            except ConversionError as exc:
                error(elements, position, result.networkSourceRows, record['Element Typ'], 'MJAP-ID', str(exc), identifier)
    for identifier, positions in shapeOwners.items():
        if len(positions) > 1:
            for position in set(positions):
                error(elements, position, result.networkSourceRows, elements.iloc[position]['Element Typ'],
                      'MJAP-ID', 'Kollision erzeugter MJAP shape-IDs.', identifier)
    return findings


def convertCleanTable(table: InputTable, logger, *, mjap: bool) -> ConversionResult:
    """Validate, exclude whole elements/groups/dependencies, then revalidate.

    Revalidation is necessary because coordinate repair may depend on the set
    of surviving station rows. Every iteration either removes rows or finishes.
    """
    from excelToCsv.pipeline import convertTable
    table = selectConversionRows(table, logger)
    types = [normalizeElementType(value) for value in textColumn(table.frame, 'ELEMENT-TYPE')]
    ids = textColumn(table.frame, 'ELEMENT ID')
    pods = textColumn(table.frame, 'Multipod')
    references = [textColumn(table.frame, col) for col in ('Station 1', 'Station 2')]
    numbers = [int(value) for value in table.rowNumbers]
    contexts = {row: {'row': row, 'elementId': ids[p], 'elementType': types[p]}
                for p, row in enumerate(numbers)}
    blocked: set[int] = set()
    findings: list[ReportedIssue] = []
    seen = set()

    def remember(entries, *, log=False):
        for severity, issue in entries:
            key = (severity, issue.row, issue.elementId, issue.field, repr(issue.value), issue.problem)
            if key not in seen:
                seen.add(key)
                findings.append((severity, replace(issue, action=
                    'Element ausgeschlossen. Angaben in der Excel-Eingabe anhand des erwarteten Werts korrigieren und erneut exportieren.')))
                if log:
                    from excelToCsv.loggingSetup import findingsLogger
                    method = findingsLogger(logger).error if severity == SEVERITY_ERROR else findingsLogger(logger).warning
                    method(findings[-1][1].render('Element ausgeschlossen.'))

    while True:
        keep = [row not in blocked for row in numbers]
        subset = InputTable(frame=table.frame.loc[keep].reset_index(drop=True),
                            rowNumbers=table.rowNumbers[keep], sheetName=table.sheetName,
                            headerRowNumber=table.headerRowNumber)
        result = convertTable(subset, logger, strict=False)
        extra = validateMjapRecords(result) if mjap else []
        entries = result.issues + extra
        remember(result.issues)
        remember(extra, log=True)
        if any(issue.row is None for _, issue in entries):
            raise ConversionError('Tabellenweite Befunde erlauben keinen sicheren Teil-Export.', issues=findings)
        newlyBlocked = {int(issue.row) for _, issue in entries} - blocked
        if not newlyBlocked:
            result.issues = sortIssues(findings)
            result.errorCount = sum(severity == SEVERITY_ERROR for severity, _ in findings)
            result.warningCount = len(findings) - result.errorCount
            result.excludedRows = sorted(blocked)
            logger.info('Teil-Export: %d Excel-Element(e) ausgeschlossen; %d Station(en), %d Netzelement(e) verbleiben.',
                        len(blocked), len(result.stations), len(result.networkElements))
            return result
        blocked.update(newlyBlocked)

        # A duplicate identity and a Multipod are indivisible logical elements.
        # Then remove all lines referring to excluded stations, including nodes.
        while True:
            badIdentities = {(types[p], ids[p]) for p, row in enumerate(numbers) if row in blocked and ids[p]}
            badPods = {pods[p] for p, row in enumerate(numbers) if row in blocked and pods[p]}
            badStations = {ids[p] for p, row in enumerate(numbers) if row in blocked and types[p] == 'SUB'}
            additions = []
            for p, row in enumerate(numbers):
                if row in blocked:
                    continue
                field, value, reason = '', '', ''
                if (types[p], ids[p]) in badIdentities:
                    field, value, reason = 'ELEMENT ID', ids[p], 'Ein weiterer Datensatz desselben Elements hat einen Befund.'
                elif pods[p] and pods[p] in badPods:
                    field, value, reason = 'Multipod', pods[p], 'Ein Bein des Dreibeins wurde ausgeschlossen; die gesamte Gruppe wird ausgeschlossen.'
                elif types[p] != 'SUB':
                    missing = [(col, refs[p]) for col, refs in zip(('Station 1', 'Station 2'), references)
                               if refs[p] and refs[p] in badStations]
                    if missing:
                        field = ', '.join(col for col, _ in missing)
                        value = ', '.join(ref for _, ref in missing)
                        reason = 'Die referenzierte Station wurde wegen eines Befunds ausgeschlossen.'
                if reason:
                    additions.append(row)
                    remember([(SEVERITY_ERROR, Issue(problem=reason, field=field, value=value,
                              expected='Alle zugehörigen Stationen und Dreibein-Beine müssen ohne Befund vorliegen.',
                              **contexts[row]))], log=True)
            if not additions:
                break
            blocked.update(additions)


def prepareCleanCompanions(stations, elements, outagesPath, projectsPath):
    """Exclude defective companion records and their dependent switchings.

    These findings identify CSV files and physical CSV row numbers, not Excel.
    A full bundle still needs at least one surviving record in each table.
    """
    from excelToCsv.mjap import _readCompanion, OUTAGE_COLUMNS, PROJECT_COLUMNS
    outages = _readCompanion(outagesPath, OUTAGE_COLUMNS, OUTAGE_COLUMNS[:6])
    projects = _readCompanion(projectsPath, PROJECT_COLUMNS, PROJECT_COLUMNS)
    findings = []
    badProjects, badOutages = set(), set()

    def record(frame, position, path, kind, field, problem):
        target = badProjects if kind == 'Projekt' else badOutages
        target.add(position)
        name = frame.iloc[position].get('Projektname' if kind == 'Projekt' else 'MJAP-ID', '')
        findings.append((SEVERITY_ERROR, Issue(problem=problem, row=frame.attrs.get('sourceRows', list(range(2, len(frame) + 2)))[position],
            elementId=name, elementType=kind, field=field,
            value=frame.iloc[position].get(field), source=str(path.resolve()),
            expected='Gültige Datumsintervalle, eindeutige IDs und vorhandene Referenzen.',
            action='Datensatz ausgeschlossen. Quelldatei korrigieren; bei ausgeschlossenen Netzelementen zuerst die Excel-Eingabe pflegen.')))

    for frame, path, kind, columns, identifiers in (
        (projects, projectsPath, 'Projekt', PROJECT_COLUMNS[2:], ('Projektname',)),
        (outages, outagesPath, 'Freischaltung', ('von', 'bis'), ('MJAP-ID', 'interne ID')),
    ):
        dates = [pd.to_datetime(frame[col], format='%d.%m.%Y', errors='coerce') for col in columns]
        duplicateMasks = {col: frame[col].duplicated(keep=False) for col in identifiers}
        for position in range(len(frame)):
            for col, parsed in zip(columns, dates):
                if pd.isna(parsed.iloc[position]):
                    record(frame, position, path, kind, col, 'Ungültiges oder fehlendes Datum.')
            if pd.notna(dates[0].iloc[position]) and pd.notna(dates[1].iloc[position]) and dates[0].iloc[position] > dates[1].iloc[position]:
                record(frame, position, path, kind, columns[0], 'Datumsintervall ist umgekehrt.')
            for col in identifiers:
                value = frame.iloc[position][col]
                if not value.strip() or value in {'NA', 'N/A', 'NaN', 'nan', 'NULL', 'null', 'None', '<NA>'}:
                    record(frame, position, path, kind, col, 'Leere oder nicht verwendbare Kennung.')
                if duplicateMasks[col].iloc[position]:
                    record(frame, position, path, kind, col, 'Doppelte Kennung; alle betroffenen Datensätze ausgeschlossen.')
    stationIds = set(stations['MJAP-ID'])
    for position, value in enumerate(projects['betroffener Standort']):
        if any(item.strip() not in stationIds for item in value.split(',')):
            record(projects, position, projectsPath, 'Projekt', 'betroffener Standort',
                   'Projekt verweist auf eine unbekannte oder ausgeschlossene Station.')
    projects = projects.loc[[p not in badProjects for p in range(len(projects))]].copy()
    projectNames = set(projects['Projektname']) | {''}
    elementIds = set(elements['MJAP-ID'])
    for position, (_, outage) in enumerate(outages.iterrows()):
        if outage['Netzelement:MJAP-ID'] not in elementIds:
            record(outages, position, outagesPath, 'Freischaltung', 'Netzelement:MJAP-ID',
                   'Freischaltung verweist auf ein unbekanntes oder ausgeschlossenes Netzelement.')
        if outage['Projekt'] not in projectNames:
            record(outages, position, outagesPath, 'Freischaltung', 'Projekt',
                   'Freischaltung verweist auf ein unbekanntes oder ausgeschlossenes Projekt.')
    outages = outages.loc[[p not in badOutages for p in range(len(outages))]].copy()
    projects['betroffener Standort'] = projects['betroffener Standort'].map(
        lambda value: ','.join(item.strip() for item in value.split(',')))
    return outages, projects, findings
