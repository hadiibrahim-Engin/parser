"""Assert the actual CSV reader semantics expected by the unchanged plugin."""
from pathlib import Path
import pandas as pd
import pytest
from conftest import elementRow, stationRow, writeExcel
from excelToCsv.pipeline import runConversion
from excelToCsv.errors import ConversionError
from excelToCsv.cli import main


def rows():
    return [stationRow(), stationRow(**{'ELEMENT ID': 'Hamburg_380'}), elementRow(),
            elementRow(**{'ELEMENT ID': 'TRA_1', 'ELEMENT-TYPE': 'TRA'})]


def testMjapCsvValuesPreserveDatesAndUnusedTopology(tmp_path, logger):
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    output = tmp_path / 'output'
    result = runConversion(workbook, output, logger, mjap=True)
    elements = pd.read_csv(result.networkElementsPath, sep=',', decimal=',')
    stations = pd.read_csv(result.stationsPath, sep=',', decimal=',')
    assert stations['lat'].iloc[0] == pytest.approx(52.459373)
    assert stations['long'].iloc[0] == pytest.approx(13.361402)
    assert elements['Station T-1:MJAP-ID'].isna().all()
    assert elements['Station T-2:MJAP-ID'].isna().all()
    assert elements['Y-Knoten-1: MJAP-ID'].isna().all()
    assert elements['IBN - Mehrfach'].str.split(';').tolist() == [['09.05.2025']] * 2
    assert elements['ABN - Mehrfach'].str.split(';').tolist() == [[' ']] * 2
    assert elements['Element Typ'].tolist() == ['Stromkreis', 'Trafo']
    assert set(p.name for p in output.glob('*.csv')) == {
        'Stationen.csv', 'Netzelemente.csv', 'Freischaltungen.csv', 'Projekte.csv'}
    assert pd.read_csv(output / 'Freischaltungen.csv').empty
    assert pd.read_csv(output / 'Projekte.csv').empty


def testMjapRejectsHeaderRenamesBeforeWriting(tmp_path, logger):
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    mapping = tmp_path / 'mapping.json'
    mapping.write_text('{"stationColumns":{"MJAP-ID":"Renamed"}}')
    with pytest.raises(ConversionError, match='canonical'):
        runConversion(workbook, tmp_path / 'out', logger, mjap=True, targetFormatPath=mapping)
    assert not (tmp_path / 'out').exists()


def testMjapRejectsIncompatibleTransformerTranslation(tmp_path, logger):
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    mapping = tmp_path / 'mapping.json'
    mapping.write_text('{"elementTypes":{"TRA":"Transformator"}}')
    with pytest.raises(ConversionError, match='TRA -> Trafo'):
        runConversion(workbook, tmp_path / 'out', logger, mjap=True, targetFormatPath=mapping)


def testMjapRejectsBrokenReferencesInLenientMode(tmp_path, logger):
    broken = rows()
    broken[2]['Station 2'] = 'Unknown'
    workbook = writeExcel(broken, tmp_path / 'network.xlsx')
    with pytest.raises(ConversionError):
        runConversion(workbook, tmp_path / 'out', logger, mjap=True)
    assert not (tmp_path / 'out').exists()


def testMjapRejectsUnrenderableSingleEndedAssets(tmp_path, logger):
    source = [*rows(), elementRow(**{'ELEMENT ID': 'GEN_1', 'ELEMENT-TYPE': 'GEN', 'Station 2': ''})]
    workbook = writeExcel(source, tmp_path / 'network.xlsx')
    with pytest.raises(ConversionError, match='both ends'):
        runConversion(workbook, tmp_path / 'out', logger, mjap=True)


def testMjapReadsCompanionTablesAndNormalizesProjectReferences(tmp_path, logger):
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    outages = tmp_path / 'outages.csv'
    projects = tmp_path / 'projects.csv'
    pd.DataFrame([{'MJAP-ID': 'FS_1', 'Netzelement:MJAP-ID': 'Amprion_TRA_1',
                   'interne ID': 'FS_1', 'von': '01.06.2028', 'bis': '02.06.2028',
                   'Projekt': 'Demo'}]).to_csv(outages, index=False)
    pd.DataFrame([{'Projektname': 'Demo', 'betroffener Standort': 'Amprion_Berlin_380, Amprion_Hamburg_380',
                   'Umsetzungzeitraum von': '01.01.2028', 'Umsetzungzeitraum bis': '31.12.2028'}]).to_csv(projects, index=False)
    output = tmp_path / 'out'
    runConversion(workbook, output, logger, mjap=True, outagesPath=outages, projectsPath=projects)
    assert pd.read_csv(output / 'Projekte.csv').iloc[0]['betroffener Standort'] == 'Amprion_Berlin_380,Amprion_Hamburg_380'
    assert pd.read_csv(output / 'Freischaltungen.csv').iloc[0]['Projekt'] == 'Demo'


def testMjapCliWritesFourTables(tmp_path):
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    assert main([str(workbook), '--mjap', '-o', str(tmp_path / 'out'), '--no-color']) == 0
    assert len(list((tmp_path / 'out').glob('*.csv'))) == 4
