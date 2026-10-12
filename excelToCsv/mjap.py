"""MJAP's exact CSV contract, including its pandas empty-value semantics."""
from __future__ import annotations

import csv
import logging
import math
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd

from excelToCsv.errors import ConversionError
from excelToCsv.normalize import DATE_OUTPUT_FORMAT
from excelToCsv.schema import NETWORK_ELEMENTS_FILENAME, STATIONS_FILENAME
from excelToCsv.targetFormat import TargetFormat
from excelToCsv.writer import _writeSingleCsv

ELEMENT_TYPES = {'LINE': 'Stromkreis', 'TRA': 'Trafo', 'TIE': 'Kuppelleitung',
                 'DCL': 'HGÜ-Strecke'}
OUTAGE_COLUMNS = ('MJAP-ID', 'Netzelement:MJAP-ID', 'interne ID', 'von', 'bis',
                  'Projekt', 'Maßnahme', 'Schaltungsart', 'Schaltung')
PROJECT_COLUMNS = ('Projektname', 'betroffener Standort',
                   'Umsetzungzeitraum von', 'Umsetzungzeitraum bis')
OPTIONAL_REFERENCES = ('Station T-1', 'Station T-2', 'Y-Knoten-1', 'Y-Knoten-2',
                       'Station T-1:MJAP-ID', 'Station T-2:MJAP-ID',
                       'Y-Knoten-1: MJAP-ID', 'Y-Knoten-2: MJAP-ID')
RESERVED_OUTAGE_COLUMNS = {'MJAP-ID_Schaltung', 'MJAP-ID_x', 'MJAP-ID_y',
                          'Element Typ', 'Station Anfang', 'Standort_von',
                          'MJAP-ID_x_orig', '_von_ts', '_bis_ts', '_IBN_ts',
                          '_ABN_eff_ts', 'base_id', 'out_idx', 'fid'}
#: Identifier spellings MJAP's pandas import would read as missing values.
NA_IDENTIFIERS = frozenset({'NA', 'N/A', 'NaN', 'nan', 'NULL', 'null', 'None', '<NA>'})


def validateShapeId(identifier: str) -> None:
    # The unchanged worker splits unquoted CSV and embeds IDs in expressions,
    # then exports a CP1252 DBF. Reject values it cannot preserve exactly.
    if (not identifier.strip() or identifier != identifier.strip() or
            any(char in identifier for char in ("'", '"', ';', ',', '\\')) or
            any(ord(char) < 32 for char in identifier)):
        raise ConversionError(f'MJAP cannot safely use this identifier in its expressions: {identifier!r}')
    try:
        encoded = identifier.encode('cp1252')
    except UnicodeEncodeError as error:
        raise ConversionError(f'MJAP shapefile identifiers must be CP1252-compatible: {identifier!r}') from error
    if len(encoded) > 254:
        raise ConversionError('MJAP shapefile identifiers cannot exceed 254 bytes.')


#: Network-element columns that describe its topology, in ``mjapShapes`` order.
TOPOLOGY_COLUMNS = ('MJAP-ID', 'Station Anfang:MJAP-ID', 'Station Ende:MJAP-ID',
                    'Station T-1:MJAP-ID', 'Y-Knoten-1: MJAP-ID')


def mjapShapes(identifier: str, start: str, end: str, third: str,
               node: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Return the edges MJAP draws for one network element and their shape IDs.

    A Y record (third station set) becomes three legs to its Y node, named
    ``<MJAP-ID>_Y1`` to ``_Y3``; any other record is one start-end line.
    """
    if third:
        return ([(station, node) for station in (start, end, third)],
                [f"{identifier}_Y{number}" for number in (1, 2, 3)])
    return [(start, end)], [identifier]


def topologyRecords(elements: pd.DataFrame):
    """Iterate the ``TOPOLOGY_COLUMNS`` values of every network element."""
    return zip(*(elements[column] for column in TOPOLOGY_COLUMNS))


def joinStandorte(values: pd.Series) -> pd.Series:
    """Rewrite each comma-separated station list without surrounding spaces."""
    return values.map(lambda value: ','.join(item.strip() for item in value.split(',')))


def parseMjapDates(values: pd.Series) -> pd.Series:
    """Parse DD.MM.YYYY dates; anything else becomes ``NaT``."""
    return pd.to_datetime(values, format=DATE_OUTPUT_FORMAT, errors='coerce')


def mjapTargetFormat(target: TargetFormat) -> TargetFormat:
    if target.stationColumns or target.networkElementColumns:
        raise ConversionError('MJAP exports require the canonical column names; column renames are not allowed.')
    types = {**ELEMENT_TYPES, **target.elementTypes}
    if types['TRA'] != 'Trafo' or any(v == 'Trafo' for k, v in types.items() if k != 'TRA'):
        raise ConversionError("MJAP exports require TRA -> Trafo; other element types cannot map to Trafo.")
    return TargetFormat(elementTypes=types)


def prepareMjapFrames(
    stations: pd.DataFrame,
    elements: pd.DataFrame,
    *,
    allowEmptyNetwork: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate retained records and preserve MJAP's CSV value conventions.

    Standalone network tables may contain only headers after row exclusion.
    The full wizard bundle still requires a connected network. Empty tables
    do not bypass validation of any records remaining in the other table.
    """
    if not allowEmptyNetwork and (stations.empty or elements.empty):
        raise ConversionError('MJAP needs at least one station and one connected network element.')
    stations, elements = stations.copy(), elements.copy()
    ids = set(stations['MJAP-ID'])
    if stations['MJAP-ID'].duplicated().any() or elements['MJAP-ID'].duplicated().any():
        raise ConversionError('MJAP requires unique station and network-element MJAP-IDs.')
    for identifier in [*ids, *elements['MJAP-ID']]:
        validateShapeId(identifier)
    for column in ('lat', 'long'):
        numeric = pd.to_numeric(stations[column], errors='coerce')
        if numeric.isna().any() or not numeric.map(math.isfinite).all():
            raise ConversionError(f'MJAP requires numeric station coordinates: {column}')
        stations[column] = stations[column].str.replace('.', ',', regex=False)
    coordinates = {identifier: (float(lat.replace(',', '.')), float(long.replace(',', '.')))
                   for identifier, lat, long in zip(stations['MJAP-ID'], stations['lat'], stations['long'])}
    for column in ('Station Anfang:MJAP-ID', 'Station Ende:MJAP-ID'):
        if not elements[column].isin(ids).all():
            raise ConversionError(f'MJAP needs existing stations on both ends: {column}')
    if elements['Station Anfang:MJAP-ID'].eq(elements['Station Ende:MJAP-ID']).any():
        raise ConversionError('MJAP cannot generate a line with identical start and end station IDs.')
    for start, end in zip(elements['Station Anfang:MJAP-ID'], elements['Station Ende:MJAP-ID']):
        if coordinates[start] == coordinates[end]:
            raise ConversionError(f'MJAP cannot generate a zero-length line: {start} / {end} have identical coordinates.')
    for frame in (stations, elements):
        start = parseMjapDates(frame['IBN'])
        end = parseMjapDates(frame['ABN'])
        if start.isna().any():
            raise ConversionError('MJAP requires a valid IBN date for every station and network element.')
        if (frame['ABN'].str.strip().ne('') & end.isna()).any():
            raise ConversionError('MJAP requires a single valid ABN date or an empty value.')
        if (start > end).any():
            raise ConversionError('MJAP lifecycle date range is reversed: IBN / ABN.')
    for column in OPTIONAL_REFERENCES:
        elements[column] = elements[column].replace({'NaN': '', ' ': ''})
    shapeIds: set[str] = set()
    for record in topologyRecords(elements):
        third, node = record[3], record[4]
        if third and (third not in ids or node not in ids):
            raise ConversionError('MJAP Y topology requires an existing third station and Y node.')
        edges, generated = mjapShapes(*record)
        for first, second in edges:
            if first == second or coordinates[first] == coordinates[second]:
                raise ConversionError(f'MJAP cannot generate a zero-length line: {first} / {second}.')
        for identifier in generated:
            validateShapeId(identifier)
            if identifier in shapeIds:
                raise ConversionError(f'MJAP generated shape-ID collision: {identifier}')
            shapeIds.add(identifier)
    # Paired one-item lists repeat existing dates. Spaces represent ONLY missing
    # dates, giving pandas a text dtype for .str.split without inventing a date.
    for frame in (stations, elements):
        for dateColumn in ('IBN', 'ABN'):
            multiple = f'{dateColumn} - Mehrfach'
            missing = frame[multiple].str.strip().eq('')
            frame.loc[missing, multiple] = frame.loc[missing, dateColumn].replace('', ' ')
            # Preserve textual values for MJAP's paired-date expansion.
            frame[dateColumn] = frame[dateColumn].replace('', ' ')
    return stations, elements


def readCompanion(path: Path | None, columns: tuple[str, ...], required: tuple[str, ...]) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame(columns=list(columns), dtype=object)
    try:
        with path.open(encoding='utf-8-sig', newline='') as handle:
            reader = csv.reader(handle)
            headers = next(reader, [])
            previousLine = reader.line_num
            sourceRows = []
            for record in reader:
                startLine = previousLine + 1
                previousLine = reader.line_num
                if record and not (len(record) == 1 and not record[0].strip()):
                    sourceRows.append(startLine)
        if len({name.casefold() for name in headers}) != len(headers):
            raise ConversionError(f'{path.name}: duplicate column names are not supported by MJAP.')
        if columns == OUTAGE_COLUMNS:
            collisions = {name for name in headers if name.casefold() in
                          {reserved.casefold() for reserved in RESERVED_OUTAGE_COLUMNS}}
        else:
            collisions = {name for name in headers if name.casefold() == 'fid'}
        if collisions:
            raise ConversionError(f'{path.name}: reserved MJAP column(s): {", ".join(sorted(collisions))}')
        frame = pd.read_csv(path, sep=',', encoding='utf-8-sig', dtype=str, keep_default_na=False)
    except (OSError, ValueError, csv.Error) as error:
        raise ConversionError(f'Cannot read MJAP companion table {path}: {error}') from error
    if len(sourceRows) != len(frame):
        raise ConversionError(f'{path.name}: cannot trace companion records to physical source rows.')
    frame.attrs['sourceRows'] = sourceRows
    missing = set(required) - set(frame.columns)
    if missing:
        raise ConversionError(f'{path.name}: missing column(s): {", ".join(sorted(missing))}')
    for column in columns:
        if column not in frame:
            frame[column] = ''
    return frame


def prepareCompanions(stations: pd.DataFrame, elements: pd.DataFrame,
                      outagesPath: Path | None, projectsPath: Path | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    outages = readCompanion(outagesPath, OUTAGE_COLUMNS, OUTAGE_COLUMNS[:6])
    projects = readCompanion(projectsPath, PROJECT_COLUMNS, PROJECT_COLUMNS)
    if outages.empty or projects.empty:
        raise ConversionError('MJAP wizard cannot import header-only Freischaltungen/Projekte sheets. Provide nonempty --freischaltungen and --projekte CSVs with real records; no dummy business data is generated.')
    for frame, columns in ((outages, ('von', 'bis')),
                           (projects, ('Umsetzungzeitraum von', 'Umsetzungzeitraum bis'))):
        parsed = [parseMjapDates(frame[column]) for column in columns]
        for column, dates in zip(columns, parsed):
            if dates.isna().any():
                raise ConversionError(f'MJAP requires valid DD.MM.YYYY dates in {column}.')
        if (parsed[0] > parsed[1]).any():
            raise ConversionError(f'MJAP date range is reversed: {columns[0]} / {columns[1]}')
    if not outages['Netzelement:MJAP-ID'].isin(elements['MJAP-ID']).all():
        raise ConversionError('Freischaltungen.csv references unknown MJAP network elements.')
    if projects['Projektname'].duplicated().any():
        raise ConversionError('MJAP needs unique project names for its project joins.')
    for frame, column in ((outages, 'MJAP-ID'), (outages, 'interne ID'), (projects, 'Projektname')):
        if frame[column].str.strip().eq('').any() or frame[column].isin(NA_IDENTIFIERS).any():
            raise ConversionError(f'MJAP requires nonempty, non-NA identifiers in {column}.')
        if frame[column].duplicated().any():
            raise ConversionError(f'MJAP requires unique identifiers in {column}.')
    if not outages['Projekt'].isin(set(projects['Projektname']) | {''}).all():
        raise ConversionError('Freischaltungen.csv references unknown project names.')
    stationIds = set(stations['MJAP-ID'])
    for value in projects['betroffener Standort']:
        references = [item.strip() for item in value.split(',')]
        if not references or any(item not in stationIds for item in references):
            raise ConversionError(f'Projekte.csv references unknown stations: {value!r}')
    projects['betroffener Standort'] = joinStandorte(projects['betroffener Standort'])
    return outages, projects


def writeMjapBundle(stations: pd.DataFrame, elements: pd.DataFrame,
                    outages: pd.DataFrame, projects: pd.DataFrame,
                    outputDir: Path, logger: logging.Logger, *, quoteAll: bool = False) -> tuple[Path, Path]:
    """Publish all four validated tables together."""
    return _writeMjapFrames({'Stationen': stations, 'Netzelemente': elements,
                            'Freischaltungen': outages, 'Projekte': projects},
                           outputDir, logger, quoteAll=quoteAll)


def writeMjapNetwork(stations: pd.DataFrame, elements: pd.DataFrame,
                     outputDir: Path, logger: logging.Logger, *, quoteAll: bool = False) -> tuple[Path, Path]:
    """Publish only the two network tables, without inventing companion data."""
    return _writeMjapFrames({'Stationen': stations, 'Netzelemente': elements},
                           outputDir, logger, quoteAll=quoteAll)


def _writeMjapFrames(frames: dict[str, pd.DataFrame], outputDir: Path,
                     logger: logging.Logger, *, quoteAll: bool) -> tuple[Path, Path]:
    """Stage the validated tables; restore old files on publish errors.

    This is not a transaction for concurrent readers or abrupt process death.
    Never run MJAP against the directory while an export is in progress.
    """
    published = []
    try:
        outputDir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.mjap-', dir=outputDir) as temporary:
            stage = Path(temporary)
            backups = stage / 'backup'
            backups.mkdir()
            for name, frame in frames.items():
                filename = f'{name}.csv'
                _writeSingleCsv(frame, stage / filename, 'utf-8-sig',
                                csv.QUOTE_ALL if quoteAll else csv.QUOTE_MINIMAL)
                target = outputDir / filename
                if target.exists():
                    shutil.copy2(target, backups / filename)
            try:
                for name in frames:
                    filename = f'{name}.csv'
                    os.replace(stage / filename, outputDir / filename)
                    published.append(filename)
            except OSError:
                for filename in reversed(published):
                    target = outputDir / filename
                    backup = backups / filename
                    if backup.exists():
                        os.replace(backup, target)
                    else:
                        target.unlink(missing_ok=True)
                raise
    except OSError as error:
        raise ConversionError(f'Failed to write MJAP CSV bundle: {error}') from error
    for name, frame in frames.items():
        logger.info('Created %s.csv (%d record(s)).', name, len(frame))
    return outputDir / STATIONS_FILENAME, outputDir / NETWORK_ELEMENTS_FILENAME
