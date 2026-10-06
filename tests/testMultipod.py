"""Excel multipods: one complete Y record and two pair records, never four."""
import logging

import pandas as pd
import pytest
from conftest import convertRows, elementRow, stationRow, writeExcel
from excelToCsv.errors import ConversionError
from excelToCsv.pipeline import runConversion
from excelToCsv.mjap import prepareMjapFrames

VIRTUAL_STATION = 'XStationK_380'


def multipodRows(node=VIRTUAL_STATION):
    stations = [stationRow(**{'ELEMENT ID': node, 'TSO': '50Hertz',
                             'Latitude': '51.1', 'Longitude': '11.6'})]
    stations += [stationRow(**{'ELEMENT ID': f'Station{x}_380',
                              'LONG-NAME': f'Umspannwerk {x}',
                              'Latitude': str(52 + i), 'Longitude': str(10 + i)})
                 for i, x in enumerate('ABC')]
    legs = [elementRow(**{'ELEMENT ID': f'LINE_00{i + 1}', 'LONG-NAME': 'Leitung xy',
                         'Station 1': node, 'Station 2': f'Station{x}_380',
                         'Multipod': node, 'UCTE CODE': f'DL00{i + 1}'})
            for i, x in enumerate('ABC')]
    return stations + legs


def testThreeLegsBecomeOneCompleteYAndTwoPairs(logger):
    result = convertRows(multipodRows(), logger)
    elements = result.networkElements
    assert len(result.stations) == 4 and len(elements) == 3
    assert elements['MJAP-ID'].tolist() == [f'Amprion_LINE_00{i}' for i in (1, 2, 3)]
    for column in ('Station Anfang', 'Station Anfang:MJAP-ID'):
        assert elements[column].tolist() == ['Amprion_StationA_380', 'Amprion_StationA_380', 'Amprion_StationB_380']
    for column in ('Station Ende', 'Station Ende:MJAP-ID'):
        assert elements[column].tolist() == ['Amprion_StationB_380', 'Amprion_StationC_380', 'Amprion_StationC_380']
    for column in ('Station T-1', 'Station T-1:MJAP-ID'):
        assert elements[column].tolist() == ['Amprion_StationC_380', '', '']
    assert elements['Y-Knoten-1'].tolist() == [VIRTUAL_STATION, '', '']
    assert elements['Y-Knoten-1: MJAP-ID'].tolist() == ['50Hertz_' + VIRTUAL_STATION, '', '']
    for column in ('Station T-2', 'Station T-2:MJAP-ID', 'Y-Knoten-2', 'Y-Knoten-2: MJAP-ID'):
        assert elements[column].eq('').all()
    for column in ('Stromkreisname - Langname', 'Stromkreisname - Kurzname'):
        assert elements[column].tolist() == ['Leitung xy', 'Leitung xy (ohne Bein StationB_380)',
                                            'Leitung xy (ohne Bein StationA_380)']
    assert result.warningCount == 0


def testExcelOrderSelectsFullRecordAndAttributesStayWithSource(logger):
    rows = multipodRows()
    for i, row in enumerate(rows[-3:]):
        row['STARTLIFETIME'] = f'202{i + 5}-05-09'
    rows = rows[:4] + [rows[6], rows[4], rows[5]]
    elements = convertRows(rows, logger).networkElements
    assert elements['MJAP-ID'].tolist() == ['Amprion_LINE_003', 'Amprion_LINE_001', 'Amprion_LINE_002']
    assert elements.iloc[0]['Station T-1:MJAP-ID'] == 'Amprion_StationB_380'
    assert elements['IBN'].tolist() == ['09.05.2027', '09.05.2025', '09.05.2026']
    assert elements['ID-UCTE'].tolist() == ['DL003', 'DL001', 'DL002']


def testReversedLegDirectionsHaveSameTopology(logger):
    rows = multipodRows()
    expected = convertRows(rows, logger).networkElements
    for row in rows[-3:]:
        row['Station 1'], row['Station 2'] = row['Station 2'], row['Station 1']
    assert convertRows(rows, logger).networkElements.equals(expected)


@pytest.mark.parametrize('node', ['StationK_380', 'StationK'])
def testExistingNodeIsNeverRenamed(logger, logCapture, node):
    result = convertRows(multipodRows(node), logger)
    assert result.networkElements.iloc[0]['Y-Knoten-1'] == node
    assert 'does not follow the expected virtual-station X naming convention' in logCapture.text(logging.WARNING)


@pytest.mark.parametrize('count', [1, 2, 4, 6])
def testIncompleteOrAmbiguousGroupsFail(logger, count):
    rows = multipodRows()
    legs = rows[4:]
    while len(legs) < count:
        legs.append({**legs[0], 'ELEMENT ID': f'EXTRA_{len(legs)}'})
    with pytest.raises(ConversionError, match='validation'):
        convertRows(rows[:4] + legs[:count], logger)


@pytest.mark.parametrize('defect', ['duplicate-end', 'node-not-end', 'loop', 'mixed-voltage', 'mixed-type', 'missing-end'])
def testInvalidTopologyFails(logger, logCapture, defect):
    rows = multipodRows()
    if defect == 'duplicate-end': rows[-1]['Station 2'] = 'StationA_380'
    if defect == 'node-not-end': rows[-1]['Station 1'] = 'StationB_380'
    if defect == 'loop': rows[-1]['Station 2'] = VIRTUAL_STATION
    if defect == 'mixed-voltage': rows[-1]['VOLTAGE-LEVEL'] = '220'
    if defect == 'mixed-type': rows[-1]['ELEMENT-TYPE'] = 'TRA'
    if defect == 'missing-end': rows[-1]['Station 2'] = 'Missing_380'
    with pytest.raises(ConversionError): convertRows(rows, logger)
    assert 'Multipod must describe exactly three unambiguous line legs.' in logCapture.text(logging.ERROR)


def testUnknownMultipodReferenceFails(logger, logCapture):
    rows = multipodRows()
    for row in rows[-3:]: row['Multipod'] = 'XDoesNotExist_380'
    with pytest.raises(ConversionError): convertRows(rows, logger)
    assert 'Multipod references an unknown virtual station.' in logCapture.text(logging.ERROR)


@pytest.mark.parametrize('omit', [False, True])
def testWithoutMultipodPlainConnectionsStayUnchanged(logger, omit):
    rows = multipodRows()
    for row in rows[-3:]:
        if omit: row.pop('Multipod')
        else: row['Multipod'] = ''
    elements = convertRows(rows, logger).networkElements
    assert elements['Station Anfang:MJAP-ID'].eq('50Hertz_' + VIRTUAL_STATION).all()
    assert elements['Y-Knoten-1'].eq('').all()
    assert elements['Station T-1:MJAP-ID'].eq('').all()
    assert elements['Stromkreisname - Langname'].eq('Leitung xy').all()


def testMapMultipodIsIgnored(logger):
    rows = multipodRows()
    expected = convertRows(rows, logger)
    for row in rows: row['Map Multipod'] = 'XDoesNotExist_380'
    actual = convertRows(rows, logger)
    assert actual.networkElements.equals(expected.networkElements)
    assert actual.stations.equals(expected.stations)


def testSeparateNodesDoNotMixGroups(logger):
    first = multipodRows()
    second = multipodRows('XOther_380')
    for row in second[1:]:
        row['ELEMENT ID'] = 'Other' + row['ELEMENT ID']
        if row['ELEMENT-TYPE'] == 'LINE': row['Station 2'] = 'Other' + row['Station 2']
    result = convertRows(first + second, logger)
    assert len(result.networkElements) == 6
    assert result.networkElements['Y-Knoten-1'].tolist() == [VIRTUAL_STATION, '', '', 'XOther_380', '', '']


def testExcelToCsvHasExactlyOneYAndNoManualCsvEditing(tmp_path, logger):
    workbook = writeExcel(multipodRows(), tmp_path / 'input.xlsx')
    outages, projects = tmp_path / 'outages.csv', tmp_path / 'projects.csv'
    pd.DataFrame([{'MJAP-ID': 'FS_1', 'Netzelement:MJAP-ID': 'Amprion_LINE_001',
                   'interne ID': 'FS_1', 'von': '01.06.2028', 'bis': '02.06.2028', 'Projekt': 'Demo'}]).to_csv(outages, index=False)
    pd.DataFrame([{'Projektname': 'Demo', 'betroffener Standort': 'Amprion_StationA_380',
                   'Umsetzungzeitraum von': '01.01.2028', 'Umsetzungzeitraum bis': '31.12.2028'}]).to_csv(projects, index=False)
    result = runConversion(workbook, tmp_path / 'csv', logger, mjap=True,
                           outagesPath=outages, projectsPath=projects)
    elements = pd.read_csv(result.networkElementsPath, encoding='utf-8-sig')
    assert len(elements) == 3
    assert elements['Y-Knoten-1: MJAP-ID'].notna().tolist() == [True, False, False]
    assert elements['Station T-1:MJAP-ID'].notna().tolist() == [True, False, False]
    assert elements['Station T-2:MJAP-ID'].isna().all()
    assert elements['Stromkreisname - Langname'].iloc[1] == 'Leitung xy (ohne Bein StationB_380)'
    assert set(pd.read_csv(tmp_path / 'csv/Freischaltungen.csv')['Netzelement:MJAP-ID']) <= set(elements['MJAP-ID'])


def testYLegZeroLengthFailsBeforePublishing(logger):
    rows = multipodRows()
    rows[0]['Latitude'], rows[0]['Longitude'] = rows[3]['Latitude'], rows[3]['Longitude']
    result = convertRows(rows, logger)
    with pytest.raises(ConversionError, match='zero-length'):
        prepareMjapFrames(result.stations, result.networkElements)


def testGeneratedYShapeIdsCannotCollide(logger):
    result = convertRows(multipodRows(), logger)
    result.networkElements.loc[1, 'MJAP-ID'] = 'Amprion_LINE_001_Y1'
    with pytest.raises(ConversionError, match='shape-ID collision'):
        prepareMjapFrames(result.stations, result.networkElements)
