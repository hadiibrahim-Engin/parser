"""MJAP's exact CSV contract, including its pandas empty-value semantics."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from excelToCsv.errors import ConversionError
from excelToCsv.targetFormat import TargetFormat
from excelToCsv.writer import _writeSingleCsv
import csv

ELEMENT_TYPES = {'LINE': 'Stromkreis', 'TRA': 'Trafo', 'TIE': 'Kuppelleitung',
                 'DCL': 'HGÜ-Strecke'}
OUTAGE_COLUMNS = ('MJAP-ID', 'Netzelement:MJAP-ID', 'interne ID', 'von', 'bis',
                  'Projekt', 'Maßnahme', 'Schaltungsart', 'Schaltung')
PROJECT_COLUMNS = ('Projektname', 'betroffener Standort',
                   'Umsetzungzeitraum von', 'Umsetzungzeitraum bis')
OPTIONAL_REFERENCES = ('Station T-1', 'Station T-2', 'Y-Knoten-1', 'Y-Knoten-2',
                       'Station T-1:MJAP-ID', 'Station T-2:MJAP-ID',
                       'Y-Knoten-1: MJAP-ID', 'Y-Knoten-2: MJAP-ID')


def mjapTargetFormat(target: TargetFormat) -> TargetFormat:
    if target.stationColumns or target.networkElementColumns:
        raise ConversionError('--mjap requires the canonical column names; column renames are not allowed.')
    types = {**ELEMENT_TYPES, **target.elementTypes}
    if types['TRA'] != 'Trafo' or any(v == 'Trafo' for k, v in types.items() if k != 'TRA'):
        raise ConversionError("--mjap requires TRA -> Trafo; other element types cannot map to Trafo.")
    return TargetFormat(elementTypes=types)


def prepareMjapFrames(stations: pd.DataFrame, elements: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Preserve real dates, and keep unused topology cells truly missing on read."""
    if stations.empty or elements.empty:
        raise ConversionError('MJAP needs at least one station and one connected network element.')
    stations, elements = stations.copy(), elements.copy()
    ids = set(stations['MJAP-ID'])
    if stations['MJAP-ID'].duplicated().any() or elements['MJAP-ID'].duplicated().any():
        raise ConversionError('MJAP requires unique station and network-element MJAP-IDs.')
    for identifier in [*ids, *elements['MJAP-ID']]:
        if any(char in identifier for char in ("'", '"', ';', ',', '\n', '\r')):
            raise ConversionError(f'MJAP cannot safely use this identifier in its expressions: {identifier!r}')
    for column in ('lat', 'long'):
        numeric = pd.to_numeric(stations[column], errors='coerce')
        if numeric.isna().any():
            raise ConversionError(f'MJAP requires numeric station coordinates: {column}')
        stations[column] = stations[column].str.replace('.', ',', regex=False)
    for column in ('Station Anfang:MJAP-ID', 'Station Ende:MJAP-ID'):
        if not elements[column].isin(ids).all():
            raise ConversionError(f'MJAP needs existing stations on both ends: {column}')
    if elements['Station Anfang:MJAP-ID'].eq(elements['Station Ende:MJAP-ID']).any():
        raise ConversionError('MJAP cannot generate a line with identical start and end station IDs.')
    for column in OPTIONAL_REFERENCES:
        elements[column] = elements[column].replace({'NaN': '', ' ': ''})
    # Paired one-item lists repeat existing dates. Spaces represent ONLY missing
    # dates, giving pandas a text dtype for .str.split without inventing a date.
    for dateColumn in ('IBN', 'ABN'):
        multiple = f'{dateColumn} - Mehrfach'
        missing = elements[multiple].str.strip().eq('')
        elements.loc[missing, multiple] = elements.loc[missing, dateColumn].replace('', ' ')
    return stations, elements


def _readCompanion(path: Path | None, columns: tuple[str, ...], required: tuple[str, ...]) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame(columns=list(columns), dtype=object)
    try:
        frame = pd.read_csv(path, sep=',', encoding='utf-8-sig', dtype=str, keep_default_na=False)
    except (OSError, ValueError) as error:
        raise ConversionError(f'Cannot read MJAP companion table {path}: {error}') from error
    missing = set(required) - set(frame.columns)
    if missing:
        raise ConversionError(f'{path.name}: missing column(s): {", ".join(sorted(missing))}')
    for column in columns:
        if column not in frame:
            frame[column] = ''
    return frame


def prepareCompanions(stations: pd.DataFrame, elements: pd.DataFrame,
                      outagesPath: Path | None, projectsPath: Path | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    outages = _readCompanion(outagesPath, OUTAGE_COLUMNS, OUTAGE_COLUMNS[:6])
    projects = _readCompanion(projectsPath, PROJECT_COLUMNS, PROJECT_COLUMNS)
    for frame, columns in ((outages, ('von', 'bis')),
                           (projects, ('Umsetzungzeitraum von', 'Umsetzungzeitraum bis'))):
        for column in columns:
            parsed = pd.to_datetime(frame[column], format='%d.%m.%Y', errors='coerce')
            if parsed.isna().any():
                raise ConversionError(f'MJAP requires valid DD.MM.YYYY dates in {column}.')
        if (pd.to_datetime(frame[columns[0]], format='%d.%m.%Y') >
                pd.to_datetime(frame[columns[1]], format='%d.%m.%Y')).any():
            raise ConversionError(f'MJAP date range is reversed: {columns[0]} / {columns[1]}')
    if not outages['Netzelement:MJAP-ID'].isin(elements['MJAP-ID']).all():
        raise ConversionError('Freischaltungen.csv references unknown MJAP network elements.')
    if projects['Projektname'].duplicated().any():
        raise ConversionError('MJAP needs unique project names for its project joins.')
    if not outages['Projekt'].isin(set(projects['Projektname']) | {''}).all():
        raise ConversionError('Freischaltungen.csv references unknown project names.')
    stationIds = set(stations['MJAP-ID'])
    for value in projects['betroffener Standort']:
        references = [item.strip() for item in value.split(',')]
        if not references or any(item not in stationIds for item in references):
            raise ConversionError(f'Projekte.csv references unknown stations: {value!r}')
    projects['betroffener Standort'] = projects['betroffener Standort'].map(
        lambda value: ','.join(item.strip() for item in value.split(',')))
    return outages, projects


def writeCompanions(outages: pd.DataFrame, projects: pd.DataFrame, outputDir: Path,
                    logger: logging.Logger) -> None:
    for name, frame in (('Freischaltungen', outages), ('Projekte', projects)):
        _writeSingleCsv(frame, outputDir / f'{name}.csv', 'utf-8-sig', csv.QUOTE_MINIMAL)
        logger.info('Created %s.csv (%d real record(s); no synthetic business data).', name, len(frame))
