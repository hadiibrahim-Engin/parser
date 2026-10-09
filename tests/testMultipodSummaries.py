"""Multipod circuit summaries are ignored before producing data findings."""
import csv
import logging

import pandas as pd
import pytest

from conftest import convertRows, elementRow, stationRow, writeExcelWithPreamble
from excelToCsv.cli import main
from excelToCsv.errors import ConversionError
from excelToCsv.pipeline import runConversion
from testMjap import rows as ordinaryRows
from testMultipod import multipodRows

GROUP_ID = 'CIRCUIT_123'


def summaryRow(**overrides):
    return elementRow(**{
        'ELEMENT ID': GROUP_ID, 'Station 1': '', 'Station 2': '',
        'TSO': '', 'STARTLIFETIME': 'invalid',
        'Interesting/Relevant for (50Hertz)': 'invalid',
        **overrides,
    })


@pytest.mark.parametrize('position', [0, 4, 7])
@pytest.mark.parametrize('marker', ['', GROUP_ID])
def testSummaryIsIgnoredWithoutFindingsRegardlessOfOrder(logger, logCapture, position, marker):
    source = multipodRows(node='YNode')
    source.insert(position, summaryRow(**{'Multipod': marker}))
    result = convertRows(source, logger)
    assert len(result.stations) == 4 and len(result.networkElements) == 3
    assert result.networkElements.iloc[0]['Y-Knoten-1'] == 'YNode'
    assert result.issues == []
    assert result.excludedRows == []
    assert result.networkSourceRows == [p + 2 for p, row in enumerate(source)
                                        if row['ELEMENT-TYPE'] == 'LINE'
                                        and row['ELEMENT ID'] != GROUP_ID]
    assert 'redundant Multipod summary' in logCapture.text(logging.INFO)
    assert logCapture.messages(logging.WARNING) == []
    assert logCapture.messages(logging.ERROR) == []


@pytest.mark.parametrize('marker', ['', GROUP_ID])
def testConnectedSummaryIsRedundantWhenThreeOtherLegsExist(logger, marker):
    source = multipodRows()
    source.append(summaryRow(**{'Station 1': 'StationA_380', 'Station 2': 'StationB_380',
                                'Multipod': marker}))
    result = convertRows(source, logger)
    assert len(result.networkElements) == 3 and result.issues == []


def testActualLegWithGroupIdAsElementIdIsKept(logger):
    source = multipodRows()
    source[4]['ELEMENT ID'] = GROUP_ID
    result = convertRows(source, logger)
    assert result.networkElements['MJAP-ID'].tolist() == ['Amprion_CIRCUIT_123',
                                                        'Amprion_LINE_002', 'Amprion_LINE_003']
    assert result.issues == []


def testRealSubStationWithGroupIdIsKept(logger):
    source = multipodRows(groupId='Real_380')
    source.append(stationRow(**{'ELEMENT ID': 'Real_380'}))
    result = convertRows(source, logger)
    assert len(result.stations) == 5
    assert result.issues == []


def testMissingEndpointsWithoutAMultipodStillProduceFinding(logger):
    orphan = elementRow(**{'ELEMENT ID': GROUP_ID, 'Station 1': '', 'Station 2': ''})
    result = convertRows(ordinaryRows() + [orphan], logger)
    assert any(issue.elementId == GROUP_ID and issue.row == 6
               and issue.problem == 'Network element has no usable station reference.'
               for _, issue in result.issues)


def testIncompleteMultipodReportsItsLegsWithoutSummaryNoise(logger):
    source = multipodRows()[:-1] + [summaryRow(**{'Multipod': GROUP_ID})]
    with pytest.raises(ConversionError) as failure:
        convertRows(source, logger)
    assert {issue.elementId for _, issue in failure.value.issues} == {'LINE_001', 'LINE_002'}
    assert all(issue.problem == 'Multipod must describe exactly three unambiguous line legs.'
               for _, issue in failure.value.issues)


@pytest.mark.parametrize('mode', [[], ['--strict'], ['--legacy']])
def testCliSummaryDoesNotCausePartialExportAndKeepsPhysicalRows(tmp_path, mode):
    source = multipodRows(node='YNode')
    source.insert(0, summaryRow(**{'Multipod': GROUP_ID}))
    workbook = writeExcelWithPreamble(source, tmp_path / 'source.xlsx', [['Title'], ['Date']])
    output = tmp_path / 'out'
    assert main([str(workbook), '-o', str(output), '--no-color', *mode]) == 0
    assert len(pd.read_csv(output / 'Netzelemente.csv')) == 3
    with (output / 'Fehlerliste.csv').open(encoding='utf-8-sig', newline='') as handle:
        assert list(csv.DictReader(handle)) == []


def testSummaryStaysIgnoredWhenItsCircuitIsExcludedOnRevalidation(tmp_path, logger):
    pod = multipodRows()
    pod[-1]['STARTLIFETIME'] = 'invalid'
    source = ordinaryRows() + [summaryRow(**{'Multipod': GROUP_ID})] + pod
    workbook = writeExcelWithPreamble(source, tmp_path / 'source.xlsx', [['Title']])
    result = runConversion(workbook, tmp_path / 'out', logger,
                           mjapNetwork=True, excludeFindings=True)
    assert result.excludedRows == [12, 13, 14]
    assert result.networkElements['MJAP-ID'].tolist() == ['Amprion_LINE_471', 'Amprion_TIE_1']
    assert not any(issue.elementId == GROUP_ID for _, issue in result.issues)


def testIgnoredTypesCannotDeclareAMultipodForAnOrphanSummary(logger):
    ignored = elementRow(**{'ELEMENT-TYPE': 'TRA', 'Multipod': GROUP_ID})
    orphan = elementRow(**{'ELEMENT ID': GROUP_ID, 'Station 1': '', 'Station 2': ''})
    result = convertRows(ordinaryRows() + [ignored, orphan], logger)
    assert any(issue.elementId == GROUP_ID for _, issue in result.issues)
