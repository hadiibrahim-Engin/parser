"""Findings point to physical input cells, including after row selection."""
import csv

import pandas as pd
import pytest

from conftest import elementRow, writeExcelWithPreamble
from excelToCsv.cli import main
from excelToCsv.issues import Issue
from excelToCsv.maintenance import sourceLocation
from testNetworkElements import twoStations

RELEVANCE = 'Interesting/Relevant for (50Hertz)'


@pytest.mark.parametrize('strict', [False, True])
def testRelevanceErrorPointsToOriginalExcelRowAndCell(tmp_path, strict):
    source = [*twoStations(),
              elementRow(**{'ELEMENT-TYPE': 'TRA', RELEVANCE: 'bad'}),
              {}, elementRow(**{RELEVANCE: 'I'}),
              elementRow(**{'ELEMENT ID': 'BAD_MARKER', RELEVANCE: '?'})]
    workbook = writeExcelWithPreamble(source, tmp_path / 'input.xlsx',
                                     [['Title'], ['Date']], sheetName="Net'z")
    output = tmp_path / 'out'
    options = ['--strict'] if strict else []
    assert main([str(workbook), '-o', str(output), '--no-color', *options]) == (2 if strict else 3)
    with (output / 'Fehlerliste.csv').open(encoding='utf-8-sig', newline='') as handle:
        records = list(csv.DictReader(handle))
    assert len(records) == 1
    finding = records[0]
    assert finding['Quelldatei'] == str(workbook.resolve())
    assert finding['Blatt'] == "Net'z"
    assert finding['Quellzeile'] == '9'
    assert finding['Fundstelle'] == "Excel-Zeile 9: 'Net''z'!N9"
    assert finding['Feld'] == RELEVANCE and finding['Wert'] == '?'
    assert finding['ELEMENT ID'] == 'BAD_MARKER'
    html = (output / 'Pflegebericht.html').read_text()
    assert 'Excel-Zeile 9:' in html and '!N9' in html
    if not strict:
        retained = pd.read_csv(output / 'Netzelemente.csv')
        assert retained['MJAP-ID'].tolist() == ['Amprion_LINE_471']
        assert retained['relevant für'].tolist() == ['50Hertz']


def testCellReferencesFollowOriginalColumnOrder(tmp_path):
    source = [*twoStations(), elementRow(**{'STARTLIFETIME': 'invalid'})]
    # Put the faulty field first; its Excel address must now be A4, not L4.
    source = [{'STARTLIFETIME': row['STARTLIFETIME'],
               **{key: value for key, value in row.items() if key != 'STARTLIFETIME'}}
              for row in source]
    workbook = writeExcelWithPreamble(source, tmp_path / 'input.xlsx', [], sheetName='Grid')
    output = tmp_path / 'out'
    assert main([str(workbook), '-o', str(output), '--no-color']) == 2
    with (output / 'Fehlerliste.csv').open(encoding='utf-8-sig', newline='') as handle:
        records = list(csv.DictReader(handle))
    finding = next(row for row in records if row['Feld'] == 'STARTLIFETIME')
    assert finding['Fundstelle'] == "Excel-Zeile 4: 'Grid'!A4"


@pytest.mark.parametrize('field, expected', [
    ('Latitude / Longitude', "Excel-Zeile 14: 'Grid'!F14, 'Grid'!AA14"),
    ('Station 1, Station 2', "Excel-Zeile 14: 'Grid'!H14, 'Grid'!I14"),
    ('Interesting / Relevant for (A, B)', "Excel-Zeile 14: 'Grid'!AB14"),
    ('MJAP-ID', "Excel-Zeile 14, Blatt 'Grid'"),
])
def testCompositeFieldsAndWholeHeadersAreResolved(field, expected):
    columns = {'Latitude': 'F', 'Longitude': 'AA', 'Station 1': 'H', 'Station 2': 'I',
               'Interesting / Relevant for (A, B)': 'AB'}
    assert sourceLocation(Issue(problem='bad', row=14, field=field), 'Grid', columns) == expected


def testCsvAndGlobalFindingsDoNotClaimAnExcelCell():
    assert sourceLocation(Issue(problem='bad', row=4, source='outages.csv'), 'Grid', {}) == 'CSV-Zeile 4'
    assert 'keine einzelne Quellzeile' in sourceLocation(Issue(problem='schema'), 'Grid', {})
