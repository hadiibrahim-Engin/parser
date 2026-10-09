"""Assert the actual CSV reader semantics expected by the unchanged plugin."""
from pathlib import Path
import pandas as pd
import pytest
from conftest import elementRow, stationRow, writeExcel
from excelToCsv.pipeline import runConversion
from excelToCsv.errors import ConversionError
from excelToCsv.cli import main


def rows():
    return [stationRow(), stationRow(**{'ELEMENT ID': 'Hamburg_380', 'Latitude': '53.55', 'Longitude': '9.99'}), elementRow(),
            elementRow(**{'ELEMENT ID': 'TIE_1', 'ELEMENT-TYPE': 'TIE'})]


def companions(tmp_path):
    outages, projects = tmp_path / 'outages.csv', tmp_path / 'projects.csv'
    pd.DataFrame([{'MJAP-ID': 'FS_1', 'Netzelement:MJAP-ID': 'Amprion_TIE_1',
                   'interne ID': 'FS_1', 'von': '01.06.2028', 'bis': '02.06.2028',
                   'Projekt': 'Demo'}]).to_csv(outages, index=False)
    pd.DataFrame([{'Projektname': 'Demo', 'betroffener Standort': 'Amprion_Berlin_380',
                   'Umsetzungzeitraum von': '01.01.2028', 'Umsetzungzeitraum bis': '31.12.2028'}]).to_csv(projects, index=False)
    return {'outagesPath': outages, 'projectsPath': projects}


def testMjapCsvValuesPreserveDatesAndUnusedTopology(tmp_path, logger):
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    output = tmp_path / 'output'
    result = runConversion(workbook, output, logger, mjap=True, **companions(tmp_path))
    elements = pd.read_csv(result.networkElementsPath, sep=',', decimal=',')
    stations = pd.read_csv(result.stationsPath, sep=',', decimal=',')
    assert stations['lat'].iloc[0] == pytest.approx(52.459373)
    assert stations['long'].iloc[0] == pytest.approx(13.361402)
    assert elements['Station T-1:MJAP-ID'].isna().all()
    assert elements['Station T-2:MJAP-ID'].isna().all()
    assert elements['Y-Knoten-1: MJAP-ID'].isna().all()
    assert elements['IBN - Mehrfach'].str.split(';').tolist() == [['09.05.2025']] * 2
    assert elements['ABN - Mehrfach'].str.split(';').tolist() == [[' ']] * 2
    assert elements['Element Typ'].tolist() == ['Stromkreis', 'Kuppelleitung']
    assert set(p.name for p in output.glob('*.csv')) == {
        'Stationen.csv', 'Netzelemente.csv', 'Freischaltungen.csv', 'Projekte.csv'}
    assert len(pd.read_csv(output / 'Freischaltungen.csv')) == 1
    assert len(pd.read_csv(output / 'Projekte.csv')) == 1


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
    source = [*rows(), elementRow(**{'ELEMENT ID': 'BUB_1', 'ELEMENT-TYPE': 'BUB', 'Station 2': ''})]
    workbook = writeExcel(source, tmp_path / 'network.xlsx')
    with pytest.raises(ConversionError, match='both ends'):
        runConversion(workbook, tmp_path / 'out', logger, mjap=True)


def testMjapReadsCompanionTablesAndNormalizesProjectReferences(tmp_path, logger):
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    outages = tmp_path / 'outages.csv'
    projects = tmp_path / 'projects.csv'
    pd.DataFrame([{'MJAP-ID': 'FS_1', 'Netzelement:MJAP-ID': 'Amprion_TIE_1',
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
    paths = companions(tmp_path)
    assert main([str(workbook), '--mjap', '--freischaltungen', str(paths['outagesPath']),
                 '--projekte', str(paths['projectsPath']), '-o', str(tmp_path / 'out'), '--no-color']) == 0
    assert {p.name for p in (tmp_path / 'out').glob('*.csv')} == {'Stationen.csv', 'Netzelemente.csv', 'Freischaltungen.csv', 'Projekte.csv', 'Fehlerliste.csv'}


@pytest.mark.parametrize('change, message', [
    ({'Latitude': '52.459373', 'Longitude': '13.361402'}, 'zero-length'),
    ({'STARTLIFETIME': ''}, 'valid IBN'),
    ({'ENDLIFETIME': '2024-01-01'}, 'reversed'),
    ({'ENDLIFETIME': '01.01.2026;01.01.2027'}, 'single valid ABN'),
    ({'ELEMENT ID': 'Киев'}, 'CP1252'),
    ({'ELEMENT ID': 'x' * 255}, '254 bytes'),
])
def testMjapRejectsUnsafeStationsBeforeWriting(tmp_path, logger, change, message):
    source = rows()
    source[1].update(change)
    if 'ELEMENT ID' in change:
        for element in source[2:]: element['Station 2'] = change['ELEMENT ID']
    workbook = writeExcel(source, tmp_path / 'network.xlsx')
    with pytest.raises(ConversionError, match=message):
        runConversion(workbook, tmp_path / 'out', logger, mjap=True, **companions(tmp_path))
    assert not (tmp_path / 'out').exists()


def testMjapRejectsDiscardedElements(tmp_path, logger):
    source = rows() + [elementRow(**{'ELEMENT ID': 'lost', 'Station 1': '', 'Station 2': ''})]
    workbook = writeExcel(source, tmp_path / 'network.xlsx')
    with pytest.raises(ConversionError, match='cannot discard'):
        runConversion(workbook, tmp_path / 'out', logger, mjap=True, **companions(tmp_path))
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('empty', [False, True])
def testMjapRejectsMissingOrHeaderOnlyCompanions(tmp_path, logger, empty):
    from excelToCsv.mjap import OUTAGE_COLUMNS, PROJECT_COLUMNS
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    paths = companions(tmp_path) if empty else {}
    if empty:
        pd.DataFrame(columns=OUTAGE_COLUMNS).to_csv(paths['outagesPath'], index=False)
        pd.DataFrame(columns=PROJECT_COLUMNS).to_csv(paths['projectsPath'], index=False)
    with pytest.raises(ConversionError, match='header-only'):
        runConversion(workbook, tmp_path / 'out', logger, mjap=True, **paths)
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('extra', ['MJAP-ID_Schaltung', 'Element Typ', 'Standort_von', 'fid'])
def testMjapRejectsGeneratedColumnCollisions(tmp_path, logger, extra):
    paths = companions(tmp_path)
    frame = pd.read_csv(paths['outagesPath'])
    frame[extra] = 'collision'
    frame.to_csv(paths['outagesPath'], index=False)
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    with pytest.raises(ConversionError, match='reserved'):
        runConversion(workbook, tmp_path / 'out', logger, mjap=True, **paths)
    assert not (tmp_path / 'out').exists()


def testMjapRejectsDuplicateHeaders(tmp_path, logger):
    paths = companions(tmp_path)
    path = paths['outagesPath']
    path.write_text(path.read_text().replace('MJAP-ID,', 'MJAP-ID,MJAP-ID,', 1))
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    with pytest.raises(ConversionError, match='duplicate column'):
        runConversion(workbook, tmp_path / 'out', logger, mjap=True, **paths)


@pytest.mark.parametrize('table, column, value, message', [
    ('outagesPath', 'Netzelement:MJAP-ID', 'Unknown', 'unknown MJAP network'),
    ('outagesPath', 'Projekt', 'Unknown', 'unknown project'),
    ('projectsPath', 'betroffener Standort', 'Unknown', 'unknown stations'),
    ('projectsPath', 'Projektname', '', 'nonempty'),
    ('outagesPath', 'interne ID', 'NULL', 'nonempty'),
    ('outagesPath', 'von', '31.02.2028', 'valid DD.MM.YYYY'),
    ('projectsPath', 'Umsetzungzeitraum bis', '31.12.2027', 'reversed'),
])
def testMjapRejectsInvalidCompanionRecords(tmp_path, logger, table, column, value, message):
    paths = companions(tmp_path)
    frame = pd.read_csv(paths[table])
    frame[column] = value
    frame.to_csv(paths[table], index=False)
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    with pytest.raises(ConversionError, match=message):
        runConversion(workbook, tmp_path / 'out', logger, mjap=True, **paths)
    assert not (tmp_path / 'out').exists()


@pytest.mark.parametrize('publishFailure', [False, True])
def testMjapWriteFailurePreservesPreviousBundle(tmp_path, logger, monkeypatch, publishFailure):
    import excelToCsv.mjap as contract
    workbook = writeExcel(rows(), tmp_path / 'network.xlsx')
    output = tmp_path / 'out'
    output.mkdir()
    names = ['Stationen.csv', 'Netzelemente.csv', 'Freischaltungen.csv', 'Projekte.csv']
    for name in names: (output / name).write_text('previous:' + name)
    if publishFailure:
        original = contract.os.replace
        def fail(source, target):
            if Path(source).name == 'Projekte.csv' and Path(target).parent == output:
                raise OSError('simulated publication failure')
            return original(source, target)
        monkeypatch.setattr(contract.os, 'replace', fail)
    else:
        original = contract._writeSingleCsv
        def fail(frame, target, *args):
            if target.name == 'Projekte.csv': raise OSError('simulated write failure')
            return original(frame, target, *args)
        monkeypatch.setattr(contract, '_writeSingleCsv', fail)
    with pytest.raises(ConversionError, match='Failed to write MJAP'):
        runConversion(workbook, output, logger, mjap=True, **companions(tmp_path))
    assert {p.name: p.read_text() for p in output.iterdir()} == {name: 'previous:' + name for name in names}
