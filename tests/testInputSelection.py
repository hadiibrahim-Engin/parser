"""Only the initial five input types enter validation or dependency closure."""
import logging

import pandas as pd
import pytest

from conftest import convertRows, elementRow, makeTable, stationRow, writeExcelWithPreamble
from excelToCsv.cli import main
from excelToCsv.inputSelection import selectConversionRows
from excelToCsv.pipeline import runConversion
from testNetworkElements import twoStations


@pytest.mark.parametrize('kind', ['TRA', 'CAP', 'GEN', 'IND', 'LOAD', 'PPL', 'PROD', 'XYZ', '', None])
@pytest.mark.parametrize('strict', [False, True])
def testOutOfScopeRowsAreIgnoredBeforeValidation(logger, kind, strict):
    ignored = elementRow(**{
        'ELEMENT-TYPE': kind, 'ELEMENT ID': '', 'TSO': '',
        'Station 1': 'Unknown', 'Station 2': '', 'STARTLIFETIME': 'bad',
        'Multipod': 'BAD_GROUP',
    })
    result = convertRows([*twoStations(), ignored, elementRow()], logger, strict=strict)
    assert result.networkElements['MJAP-ID'].tolist() == ['Amprion_LINE_471']
    assert result.networkSourceRows == [5]
    assert result.issues == []
    assert result.excludedRows == []


@pytest.mark.parametrize('kind', ['LINE', 'TIE', 'BUB', 'DCL', ' line ', 'sub'])
def testSupportedTypesSurviveSelection(logger, kind):
    row = (stationRow(**{'ELEMENT ID': 'Other_380', 'ELEMENT-TYPE': kind})
           if kind == 'sub' else elementRow(**{'ELEMENT-TYPE': kind}))
    result = convertRows([*twoStations(), row], logger)
    assert len(result.stations) + len(result.networkElements) == 3
    assert result.issues == []


def testIgnoredDuplicateNeverExcludesASupportedElement(tmp_path, logger):
    ignored = elementRow(**{'ELEMENT-TYPE': 'TRA', 'STARTLIFETIME': 'invalid'})
    workbook = writeExcelWithPreamble(
        [*twoStations(), ignored, elementRow()], tmp_path / 'input.xlsx', [['Title'], ['Note']])
    result = runConversion(workbook, tmp_path / 'out', logger,
                           mjapNetwork=True, excludeFindings=True)
    assert result.networkSourceRows == [7]
    assert result.networkElements['MJAP-ID'].tolist() == ['Amprion_LINE_471']
    assert result.issues == []
    assert result.excludedRows == []


@pytest.mark.parametrize('mode', [[], ['--strict'], ['--legacy']])
def testCliReportsIgnoredTypesAsCleanExport(tmp_path, mode):
    source = [*twoStations(), elementRow(),
              elementRow(**{'ELEMENT-TYPE': 'UNKNOWN', 'STARTLIFETIME': 'invalid'})]
    workbook = writeExcelWithPreamble(source, tmp_path / 'input.xlsx', [['Title']])
    output = tmp_path / 'out'
    assert main([str(workbook), '-o', str(output), '--no-color', *mode]) == 0
    assert len(pd.read_csv(output / 'Netzelemente.csv')) == 1
    assert pd.read_csv(output / 'Fehlerliste.csv').empty


def testSelectionKeepsSheetHeaderAndPhysicalRows(logger, logCapture):
    table = makeTable([stationRow(), elementRow(**{'ELEMENT-TYPE': 'TRA'}),
                       elementRow()], logger)
    table.headerRowNumber = 12
    selected = selectConversionRows(table, logger)
    assert selected.sheetName == table.sheetName
    assert selected.headerRowNumber == 12
    assert selected.rowNumbers.tolist() == [2, 4]
    assert selectConversionRows(selected, logger) is selected
    assert 'TRA: 1' in logCapture.text(logging.INFO)
