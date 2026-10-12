"""MJAP import checks and MJAP's CSV value conventions, applied before writing."""
from __future__ import annotations

import math

import pandas as pd

from excelToCsv.errors import ConversionError
from excelToCsv.normalize import DATE_OUTPUT_FORMAT

ELEMENT_TYPES = {'LINE': 'Stromkreis', 'TIE': 'Kuppelleitung',
                 'DCL': 'HGÜ-Strecke'}


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


def parseMjapDates(values: pd.Series) -> pd.Series:
    """Parse DD.MM.YYYY dates; anything else becomes ``NaT``."""
    return pd.to_datetime(values, format=DATE_OUTPUT_FORMAT, errors='coerce')


def prepareMjapFrames(
    stations: pd.DataFrame,
    elements: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate retained records and apply the fixed MJAP CSV conventions."""
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
    elements['Element Typ'] = elements['Element Typ'].replace(ELEMENT_TYPES)
    return stations, elements
