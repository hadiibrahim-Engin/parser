"""Partial export is safe only when its entire retained graph imports in MJAP."""
import csv
from pathlib import Path

import pandas as pd
import pytest

from conftest import elementRow, stationRow, writeExcel, writeExcelWithPreamble
from testMjap import rows, companions
from testMultipod import multipodRows
from excelToCsv.cli import main
from excelToCsv.pipeline import runConversion
from excelToCsv.errors import ConversionError
from excelToCsv.maintenance import CSV_COLUMNS


def reports(output):
    with (output / 'Fehlerliste.csv').open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize('defect', ['unknown-type', 'missing-ref', 'unknown-ref', 'invalid-date',
                                  'missing-ibn', 'reversed-dates', 'unsafe-id', 'identical-ends', 'multiple-abn'])
def testBadElementIsExcludedAndGoodElementsArePublished(tmp_path, defect):
    source = rows()
    bad = elementRow(**{'ELEMENT ID': 'BAD'})
    if defect == 'unknown-type': bad['ELEMENT-TYPE'] = 'NO_SUCH_TYPE'
    if defect == 'missing-ref': bad['Station 2'] = ''
    if defect == 'unknown-ref': bad['Station 2'] = 'Missing_380'
    if defect == 'invalid-date': bad['STARTLIFETIME'] = '31.02.2025'
    if defect == 'missing-ibn': bad['STARTLIFETIME'] = ''
    if defect == 'reversed-dates': bad['ENDLIFETIME'] = '01.01.2020'
    if defect == 'multiple-abn': bad['ENDLIFETIME'] = '01.01.2026;01.01.2027'
    if defect == 'unsafe-id': bad['ELEMENT ID'] = "BAD'ID"
    if defect == 'identical-ends': bad['Station 2'] = bad['Station 1']
    workbook = writeExcel(source + [bad], tmp_path/'source.xlsx')
    original = workbook.read_bytes()
    output = tmp_path/'output'
    assert main([str(workbook), '-o', str(output), '--detail', '--no-color']) == 3
    assert workbook.read_bytes() == original
    assert pd.read_csv(output/'Netzelemente.csv')['MJAP-ID'].tolist() == ['Amprion_LINE_471', 'Amprion_TRA_1']
    records = reports(output)
    assert any(record['ELEMENT ID'] == bad['ELEMENT ID'] and record['Quellzeile'] == '6' for record in records)
    assert all(record['Pflegehinweis'] for record in records)
    assert 'Export veröffentlicht' in (output/'Pflegebericht.html').read_text()


@pytest.mark.parametrize('defect', ['warning-name', 'warning-coordinate', 'invalid-coordinate', 'missing-owner', 'missing-ibn'])
def testBadStationAndEveryDependentLineAreExcluded(tmp_path, defect, logger):
    station = stationRow(**{'ELEMENT ID': 'Pflege_380', 'Latitude': '50.123', 'Longitude': '8.456'})
    if defect == 'warning-name': station['ELEMENT ID'] = 'Pflege'
    if defect == 'warning-coordinate': station['Latitude'] = '50123456'
    if defect == 'invalid-coordinate': station['Latitude'] = 'abc'
    if defect == 'missing-owner': station['TSO'] = ''
    if defect == 'missing-ibn': station['STARTLIFETIME'] = ''
    dependent = elementRow(**{'ELEMENT ID': 'DEPENDENT', 'Station 2': station['ELEMENT ID']})
    workbook = writeExcel(rows() + [station, dependent], tmp_path/'source.xlsx')
    result = runConversion(workbook, tmp_path/'out', logger, mjapNetwork=True, excludeFindings=True)
    assert result.excludedRows == [6, 7]
    assert len(result.stations) == 2 and len(result.networkElements) == 2
    assert any('referenzierte Station' in issue.problem and issue.row == 7 for _, issue in result.issues)
    if defect.startswith('warning'):
        assert result.warningCount >= 1


@pytest.mark.parametrize('defect', ['bad-leg-date', 'missing-leg-ref', 'two-legs', 'bad-x', 'bad-outer'])
def testWholeDreibeinIsExcludedAndUnrelatedNetworkSurvives(tmp_path, logger, defect):
    pod = multipodRows()
    if defect == 'bad-leg-date': pod[-1]['STARTLIFETIME'] = 'bad'
    if defect == 'missing-leg-ref': pod[-1]['Station 2'] = ''
    if defect == 'two-legs': pod.pop()
    if defect == 'bad-x': pod[0]['Latitude'] = 'bad'
    if defect == 'bad-outer': pod[3]['TSO'] = ''
    workbook = writeExcel(rows() + pod, tmp_path/'source.xlsx')
    result = runConversion(workbook, tmp_path/'out', logger, mjapNetwork=True, excludeFindings=True)
    assert result.networkElements['MJAP-ID'].tolist() == ['Amprion_LINE_471', 'Amprion_TRA_1']
    badIds = {issue.elementId for _, issue in result.issues}
    assert {record['ELEMENT ID'] for record in pod if record['ELEMENT-TYPE'] != 'SUB'} <= badIds


def testEveryIdenticalDuplicateIsExcludedWithoutDroppingUnrelatedLines(tmp_path, logger):
    duplicate = elementRow(**{'ELEMENT ID': 'DUP'})
    workbook = writeExcel(rows() + [duplicate, duplicate.copy()], tmp_path/'source.xlsx')
    result = runConversion(workbook, tmp_path/'out', logger, mjapNetwork=True, excludeFindings=True)
    assert result.excludedRows == [6, 7]
    assert len(result.networkElements) == 2
    assert {issue.row for _, issue in result.issues if issue.elementId == 'DUP'} == {6, 7}


def testShapeIdCollisionExcludesBothOwnersAndWholeYGroup(tmp_path, logger):
    collision = elementRow(**{'ELEMENT ID': 'LINE_001_Y1'})
    workbook = writeExcel(rows() + multipodRows() + [collision], tmp_path/'source.xlsx')
    result = runConversion(workbook, tmp_path/'out', logger, mjapNetwork=True, excludeFindings=True)
    assert len(result.networkElements) == 2
    assert any('Kollision' in issue.problem for _, issue in result.issues)


def testReportsKeepPhysicalExcelRowsWithPreambleAndBlankRows(tmp_path):
    bad = elementRow(**{'ELEMENT ID': 'BAD', 'STARTLIFETIME': 'invalid'})
    workbook = writeExcelWithPreamble(rows() + [{}] + [bad], tmp_path/'source.xlsx', [['Titel'], ['Hinweis']])
    output = tmp_path/'out'
    assert main([str(workbook), '-o', str(output), '--no-color']) == 3
    assert {record['Quellzeile'] for record in reports(output) if record['ELEMENT ID'] == 'BAD'} == {'9'}


def testAllExcludedWritesReportsButNeverReplacesOldNetwork(tmp_path):
    source = rows()
    source[2]['STARTLIFETIME'] = source[3]['STARTLIFETIME'] = ''
    workbook = writeExcel(source, tmp_path/'source.xlsx')
    output = tmp_path/'out'; output.mkdir()
    for name in ('Stationen.csv', 'Netzelemente.csv'):
        (output/name).write_text('previous')
    assert main([str(workbook), '-o', str(output), '--no-color']) == 2
    assert all((output/name).read_text() == 'previous' for name in ('Stationen.csv', 'Netzelemente.csv'))
    assert len(reports(output)) >= 3
    assert 'Export abgebrochen' in (output/'Pflegebericht.html').read_text()


def testCleanRunAutomaticallyWritesHeaderOnlyFindingsCsv(tmp_path):
    workbook = writeExcel(rows(), tmp_path/'source.xlsx')
    output = tmp_path/'out'
    assert main([str(workbook), '-o', str(output), '--no-color']) == 0
    assert reports(output) == []
    with (output/'Fehlerliste.csv').open(encoding='utf-8-sig') as handle:
        assert next(csv.reader(handle)) == list(CSV_COLUMNS)
    assert (output/'Fehlerliste.csv').read_bytes().startswith(b'\xef\xbb\xbf')


def testReportEscapesExcelValuesAndIncludesOriginalInput(tmp_path):
    workbook = writeExcel(rows() + [elementRow(**{'ELEMENT ID': 'BAD', 'STARTLIFETIME': '<script>alert(1)</script>'})], tmp_path/'source.xlsx')
    output = tmp_path/'out'
    assert main([str(workbook), '-o', str(output), '--no-color']) == 3
    html = (output/'Pflegebericht.html').read_text()
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert 'Eingabewerte der betroffenen Elemente' in html


def testSchemaFailureAutomaticallyCreatesMaintenanceReports(tmp_path):
    workbook = tmp_path/'source.xlsx'
    pd.DataFrame([{'ELEMENT ID': 'Bad'}]).to_excel(workbook, index=False)
    output = tmp_path/'out'
    assert main([str(workbook), '-o', str(output), '--no-color']) == 2
    assert any('Missing required' in record['Problem'] for record in reports(output))
    assert not (output/'Netzelemente.csv').exists()


def testCompanionsExcludeLocalDefectsAndReferencingOutages(tmp_path, logger):
    workbook = writeExcel(rows(), tmp_path/'source.xlsx')
    paths = companions(tmp_path)
    projects = pd.read_csv(paths['projectsPath'], keep_default_na=False)
    badProject = {**projects.iloc[0].to_dict(), 'Projektname': 'BAD_PROJECT', 'betroffener Standort': 'UNKNOWN'}
    pd.concat([projects, pd.DataFrame([badProject])]).to_csv(paths['projectsPath'], index=False)
    outages = pd.read_csv(paths['outagesPath'], keep_default_na=False)
    badOutage = {**outages.iloc[0].to_dict(), 'MJAP-ID': 'BAD_OUTAGE', 'interne ID': 'BAD', 'Projekt': 'BAD_PROJECT'}
    pd.concat([outages, pd.DataFrame([badOutage])]).to_csv(paths['outagesPath'], index=False)
    output = tmp_path/'out'
    result = runConversion(workbook, output, logger, mjap=True, excludeFindings=True, **paths)
    assert result.excludedCompanionCount == 2
    assert len(pd.read_csv(output/'Projekte.csv')) == len(pd.read_csv(output/'Freischaltungen.csv')) == 1
    records = reports(output)
    assert {Path(record['Quelldatei']).name for record in records} == {'outages.csv', 'projects.csv'}
    assert {record['Quellzeile'] for record in records} == {'3'}
    assert all(record['Blatt'] == '' for record in records)


def testFullBundleDoesNotPublishWhenAllCompanionsAreExcluded(tmp_path, logger):
    workbook = writeExcel(rows(), tmp_path/'source.xlsx')
    paths = companions(tmp_path)
    frame = pd.read_csv(paths['projectsPath']); frame['betroffener Standort'] = 'UNKNOWN'
    frame.to_csv(paths['projectsPath'], index=False)
    output = tmp_path/'out'
    with pytest.raises(ConversionError, match='fehlen gültige'):
        runConversion(workbook, output, logger, mjap=True, excludeFindings=True, **paths)
    assert not (output/'Stationen.csv').exists()
    assert reports(output)


def testStrictMjapAlsoRejectsWarningOnlyInput(tmp_path):
    workbook = writeExcel(rows() + [stationRow(**{'ELEMENT ID': 'Pflege'})], tmp_path/'source.xlsx')
    output = tmp_path/'out'
    assert main([str(workbook), '-o', str(output), '--strict', '--no-color']) == 2
    assert not (output/'Stationen.csv').exists()
    assert any(record['Schweregrad'] == 'WARNING' for record in reports(output))


def testCompanionReportKeepsPhysicalRowsAcrossBlankLinesAndMultilineFields(tmp_path, logger):
    workbook = writeExcel(rows(), tmp_path/'source.xlsx')
    paths = companions(tmp_path)
    project = pd.read_csv(paths['projectsPath']).iloc[0].to_dict()
    bad = [{**project, 'Projektname': 'BAD\nMULTILINE', 'betroffener Standort': 'UNKNOWN'},
           {**project, 'Projektname': 'BAD_NEXT', 'betroffener Standort': 'UNKNOWN'}]
    pd.DataFrame([project, *bad]).to_csv(paths['projectsPath'], index=False)
    contents = paths['projectsPath'].read_text().splitlines(keepends=True)
    paths['projectsPath'].write_text(contents[0] + '\n' + ''.join(contents[1:]))
    output = tmp_path/'out'
    runConversion(workbook, output, logger, mjap=True, excludeFindings=True, **paths)
    assert {record['Quellzeile'] for record in reports(output)} == {'4', '6'}
