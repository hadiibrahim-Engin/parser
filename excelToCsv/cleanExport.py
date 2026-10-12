"""Exclude unusable records and dependencies; keep records with warnings."""
from __future__ import annotations

import math
from dataclasses import replace
from collections import defaultdict, deque
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from excelToCsv.errors import ConversionError
from excelToCsv.issues import Issue, ReportedIssue, SEVERITY_ERROR, sortIssues
from excelToCsv.inputSelection import selectConversionRows
from excelToCsv.lifecycle import generatedLifecycleDates
from excelToCsv.loggingSetup import findingsLogger
from excelToCsv.mjap import (
    NA_IDENTIFIERS, OUTAGE_COLUMNS, PROJECT_COLUMNS,
    joinStandorte, mjapShapes, parseMjapDates, readCompanion, topologyRecords, validateShapeId,
)
from excelToCsv.reader import InputTable, elementTypeColumn, textColumn
from excelToCsv.schema import (
    COL_ELEMENT_ID, COL_MULTIPOD, COL_STATION_1, COL_STATION_2, STATION_TYPE,
)

if TYPE_CHECKING:
    from excelToCsv.pipeline import ConversionResult


def validateMjapRecords(result: ConversionResult) -> list[ReportedIssue]:
    """Attach MJAP-only defects to actual source rows before publication.

    The final shared prepareMjapFrames validator remains the publication guard.
    This pass provides per-element context so a local defect can be quarantined.
    """
    findings: list[ReportedIssue] = []

    def error(position, source, kind, field, problem, value=None):
        findings.append((SEVERITY_ERROR, Issue(
            problem=problem, row=int(source[position]),
            elementId=result.sourceElementIds[int(source[position])],
            elementType=kind, field=field, value=value,
            expected="Gültiger MJAP-Datensatz mit eindeutiger ID und vorhandenen Anschlüssen.",
        )))

    for frame, source, kind in (
        (result.stations, result.stationSourceRows, 'SUB'),
        (result.networkElements, result.networkSourceRows, ''),
    ):
        identifiers = frame['MJAP-ID'].tolist()
        kinds = [kind] * len(frame) if kind else frame['Element Typ'].tolist()
        for position, identifier in enumerate(identifiers):
            try:
                validateShapeId(identifier)
            except ConversionError as exc:
                error(position, source, kinds[position], 'MJAP-ID', str(exc), identifier)
        for position in np.flatnonzero(frame['MJAP-ID'].duplicated(keep=False).to_numpy()):
            error(position, source, kinds[position], 'MJAP-ID', 'Doppelte MJAP-ID.', identifiers[position])

    stations = result.stations
    ids = set(stations['MJAP-ID'])
    coordinates = {}
    numericCoordinates = stations[['lat', 'long']].apply(pd.to_numeric, errors='coerce')
    for position, (identifier, lat, long, pair) in enumerate(zip(
            stations['MJAP-ID'], stations['lat'], stations['long'],
            numericCoordinates.itertuples(index=False, name=None))):
        if all(math.isfinite(value) for value in pair):
            coordinates[identifier] = pair
        else:
            error(position, result.stationSourceRows, 'SUB', 'Latitude / Longitude',
                  'MJAP benötigt endliche numerische Koordinaten.', f"{lat} / {long}")

    shapeOwners = defaultdict(list)
    elements = result.networkElements
    elementKinds = elements['Element Typ'].tolist()
    for position, record in enumerate(topologyRecords(elements)):
        _, start, end, third, _ = record
        kind = elementKinds[position]
        edges, generated = mjapShapes(*record)
        for first, second in ([(start, end), *edges] if third else edges):
            if first not in ids or second not in ids:
                error(position, result.networkSourceRows, kind,
                      'Station 1 / Station 2 / Multipod', 'Anschlussstation fehlt im MJAP-Netz.', f'{first} / {second}')
            elif first == second or (first in coordinates and second in coordinates
                                      and coordinates[first] == coordinates[second]):
                error(position, result.networkSourceRows, kind,
                      'Station 1 / Station 2 / Multipod', 'Leitung mit identischen Endpunkten oder Koordinaten.', f'{first} / {second}')
        for identifier in generated:
            shapeOwners[identifier].append(position)
            try:
                validateShapeId(identifier)
            except ConversionError as exc:
                error(position, result.networkSourceRows, kind, 'MJAP-ID', str(exc), identifier)
    for identifier, positions in shapeOwners.items():
        if len(positions) > 1:
            for position in set(positions):
                error(position, result.networkSourceRows, elementKinds[position],
                      'MJAP-ID', 'Kollision erzeugter MJAP shape-IDs.', identifier)
    return findings


def convertCleanTable(table: InputTable, logger, *, mjap: bool) -> ConversionResult:
    """Convert once, remove unusable rows and their dependencies, keep warnings.

    Coordinates are repaired from the complete source column. Excluding an
    unrelated row must not change a repaired location or a virtual node's identity.
    """
    from excelToCsv.pipeline import convertTable  # pipeline imports this module

    table = selectConversionRows(table, logger)
    result = convertTable(table, logger, lifecycleDates=generatedLifecycleDates() if mjap else None)
    extra = validateMjapRecords(result) if mjap else []
    findings = result.issues + extra
    for _, issue in extra:
        findingsLogger(logger).error(issue.render('Element ausgeschlossen.'))
    if any(severity == SEVERITY_ERROR and issue.row is None for severity, issue in findings):
        raise ConversionError('Tabellenweite Befunde erlauben keinen sicheren Teil-Export.', issues=findings)

    numbers = [int(row) for row in table.rowNumbers]
    exported = set(result.stationSourceRows) | set(result.networkSourceRows)
    blocked = (set(numbers) - exported) | {
        int(issue.row) for severity, issue in findings
        if severity == SEVERITY_ERROR and issue.row is not None
    }
    types = elementTypeColumn(table.frame)
    ids = textColumn(table.frame, COL_ELEMENT_ID)
    pods = textColumn(table.frame, COL_MULTIPOD)
    identities, groups, stationUsers = defaultdict(list), defaultdict(list), defaultdict(list)
    rowInfo = {}
    for position, row in enumerate(numbers):
        kind, identifier = types[position], ids[position]
        pod = pods[position] if kind != STATION_TYPE else ''
        rowInfo[row] = (kind, identifier, pod)
        if identifier:
            identities[kind, identifier].append(row)
        if pod:
            groups[pod].append(row)
    for column in (COL_STATION_1, COL_STATION_2):
        for row, kind, station in zip(numbers, types, textColumn(table.frame, column)):
            if kind != STATION_TYPE and station:
                stationUsers[station].append((row, column))

    pending = deque(sorted(blocked))

    def exclude(row, field, value, problem):
        if row in blocked:
            return
        blocked.add(row)
        pending.append(row)
        kind, identifier, _ = rowInfo[row]
        issue = Issue(problem=problem, row=row, elementId=identifier, elementType=kind,
                      field=field, value=value,
                      expected='Alle zugehörigen Stationen und Dreibein-Beine müssen verwendbar sein.')
        findings.append((SEVERITY_ERROR, issue))
        findingsLogger(logger).error(issue.render('Element ausgeschlossen.'))

    while pending:
        kind, identifier, pod = rowInfo[pending.popleft()]
        for row in identities.pop((kind, identifier), []):
            exclude(row, COL_ELEMENT_ID, identifier,
                    'Ein weiterer Datensatz desselben Elements ist nicht verwendbar.')
        for row in groups.pop(pod, []):
            exclude(row, COL_MULTIPOD, pod,
                    'Ein Bein des Dreibeins wurde ausgeschlossen; die gesamte Gruppe wird ausgeschlossen.')
        if kind == STATION_TYPE:
            for row, column in stationUsers.pop(identifier, []):
                exclude(row, column, identifier,
                        'Die referenzierte Station ist nicht verwendbar und wurde ausgeschlossen.')

    def retained(frame, sourceRows):
        keep = [row not in blocked for row in sourceRows]
        return frame.loc[keep].reset_index(drop=True), [row for row, kept in zip(sourceRows, keep) if kept]

    result.stations, result.stationSourceRows = retained(result.stations, result.stationSourceRows)
    result.networkElements, result.networkSourceRows = retained(result.networkElements, result.networkSourceRows)
    result.issues = sortIssues([
        (severity, replace(issue, action=
            'Element ausgeschlossen. Angaben in der Excel-Eingabe anhand des erwarteten Werts korrigieren und erneut exportieren.'))
        if issue.row in blocked else (severity, issue)
        for severity, issue in findings
    ])
    result.excludedRows = sorted(blocked)
    logger.info('Teil-Export: %d Excel-Element(e) ausgeschlossen; %d Station(en), %d Netzelement(e) verbleiben.',
                len(blocked), len(result.stations), len(result.networkElements))
    return result


def prepareCleanCompanions(stations, elements, outagesPath, projectsPath):
    """Exclude defective companion records and their dependent switchings.

    These findings identify CSV files and physical CSV row numbers, not Excel.
    A full bundle still needs at least one surviving record in each table.
    """
    outages = readCompanion(outagesPath, OUTAGE_COLUMNS, OUTAGE_COLUMNS[:6])
    projects = readCompanion(projectsPath, PROJECT_COLUMNS, PROJECT_COLUMNS)
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
        dates = [parseMjapDates(frame[col]).tolist() for col in columns]
        values = {col: frame[col].tolist() for col in identifiers}
        duplicateMasks = {col: frame[col].duplicated(keep=False).tolist() for col in identifiers}
        for position in range(len(frame)):
            for col, parsed in zip(columns, dates):
                if pd.isna(parsed[position]):
                    record(frame, position, path, kind, col, 'Ungültiges oder fehlendes Datum.')
            start, end = dates[0][position], dates[1][position]
            if pd.notna(start) and pd.notna(end) and start > end:
                record(frame, position, path, kind, columns[0], 'Datumsintervall ist umgekehrt.')
            for col in identifiers:
                value = values[col][position]
                if not value.strip() or value in NA_IDENTIFIERS:
                    record(frame, position, path, kind, col, 'Leere oder nicht verwendbare Kennung.')
                if duplicateMasks[col][position]:
                    record(frame, position, path, kind, col, 'Doppelte Kennung; alle betroffenen Datensätze ausgeschlossen.')
    stationIds = set(stations['MJAP-ID'])
    for position, value in enumerate(projects['betroffener Standort']):
        if any(item.strip() not in stationIds for item in value.split(',')):
            record(projects, position, projectsPath, 'Projekt', 'betroffener Standort',
                   'Projekt verweist auf eine unbekannte oder ausgeschlossene Station.')
    projects = projects.loc[[p not in badProjects for p in range(len(projects))]].copy()
    projectNames = set(projects['Projektname']) | {''}
    elementIds = set(elements['MJAP-ID'])
    for position, (element, project) in enumerate(zip(outages['Netzelement:MJAP-ID'], outages['Projekt'])):
        if element not in elementIds:
            record(outages, position, outagesPath, 'Freischaltung', 'Netzelement:MJAP-ID',
                   'Freischaltung verweist auf ein unbekanntes oder ausgeschlossenes Netzelement.')
        if project not in projectNames:
            record(outages, position, outagesPath, 'Freischaltung', 'Projekt',
                   'Freischaltung verweist auf ein unbekanntes oder ausgeschlossenes Projekt.')
    outages = outages.loc[[p not in badOutages for p in range(len(outages))]].copy()
    projects['betroffener Standort'] = joinStandorte(projects['betroffener Standort'])
    return outages, projects, findings
