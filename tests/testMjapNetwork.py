"""The user's simple Excel + output-dir command must use the MJAP contract."""
from pathlib import Path
import pandas as pd
import pytest
from conftest import writeExcel
from testMjap import rows, companions
from testMultipod import multipodRows
from excelToCsv.cli import main
from excelToCsv.pipeline import runConversion
from excelToCsv.errors import ConversionError


@pytest.mark.parametrize('source', [rows, multipodRows])
def testDefaultCommandWritesOnlySafeNetworkCsvs(tmp_path, source):
    workbook = writeExcel(source(), tmp_path / 'input.xlsx')
    output = tmp_path / 'out'
    assert main([str(workbook), '-o', str(output), '--detail', '--no-color']) == 0
    assert {p.name for p in output.iterdir()} == {'Stationen.csv', 'Netzelemente.csv'}
    assert (output / 'Stationen.csv').read_bytes().startswith(b'\xef\xbb\xbf')
    stations = pd.read_csv(output / 'Stationen.csv', decimal=',')
    elements = pd.read_csv(output / 'Netzelemente.csv', decimal=',')
    assert pd.api.types.is_numeric_dtype(stations['lat'])
    assert pd.api.types.is_numeric_dtype(stations['long'])
    assert elements['Station T-2:MJAP-ID'].isna().all()
    assert elements['Y-Knoten-2: MJAP-ID'].isna().all()
    assert elements['IBN - Mehrfach'].str.split(';').tolist() == [['09.05.2025']] * len(elements)
    if source is multipodRows:
        assert elements['Station T-1:MJAP-ID'].notna().tolist() == [True, False, False]
        assert elements['Y-Knoten-1: MJAP-ID'].notna().tolist() == [True, False, False]
    else:
        assert elements['Station T-1:MJAP-ID'].isna().all()
        assert elements['Y-Knoten-1: MJAP-ID'].isna().all()
        assert elements['Element Typ'].tolist() == ['Stromkreis', 'Trafo']


def testLegacyModeIsExplicitAndRetainsOldPlaceholders(tmp_path):
    workbook = writeExcel(rows(), tmp_path / 'input.xlsx')
    output = tmp_path / 'out'
    assert main([str(workbook), '-o', str(output), '--legacy', '--no-color']) == 0
    assert pd.read_csv(output / 'Netzelemente.csv')['Station T-1:MJAP-ID'].eq(' ').all()


@pytest.mark.parametrize('defect', ['station-reference', 'missing-ibn', 'zero-length'])
def testDefaultCommandRejectsBrokenInputBeforeReplacingOldCsvs(tmp_path, defect, capsys):
    source = rows()
    if defect == 'station-reference': source[2]['Station 2'] = 'Unknown_380'
    if defect == 'missing-ibn': source[2]['STARTLIFETIME'] = ''
    if defect == 'zero-length': source[1]['Latitude'], source[1]['Longitude'] = source[0]['Latitude'], source[0]['Longitude']
    workbook = writeExcel(source, tmp_path / 'input.xlsx')
    output = tmp_path / 'out'; output.mkdir()
    for name in ('Stationen.csv', 'Netzelemente.csv'): (output / name).write_text('previous:'+name)
    assert main([str(workbook), '-o', str(output), '--details', '--no-color']) == 2
    assert 'Export aborted:' in capsys.readouterr().err
    assert {p.name:p.read_text() for p in output.iterdir()} == {
        name:'previous:'+name for name in ('Stationen.csv', 'Netzelemente.csv')}


@pytest.mark.parametrize('publish', [False, True])
def testTwoFilePublicationFailureRollsBack(tmp_path, logger, monkeypatch, publish):
    import excelToCsv.mjap as contract
    workbook = writeExcel(rows(), tmp_path / 'input.xlsx')
    output = tmp_path / 'out'; output.mkdir()
    names = ('Stationen.csv', 'Netzelemente.csv', 'Freischaltungen.csv', 'Projekte.csv')
    for name in names: (output/name).write_text('previous:'+name)
    if publish:
        original = contract.os.replace
        def fail(source, target):
            if Path(source).name == 'Netzelemente.csv' and Path(target).parent == output:
                raise OSError('simulated publication failure')
            return original(source, target)
        monkeypatch.setattr(contract.os, 'replace', fail)
    else:
        original = contract._writeSingleCsv
        def fail(frame, target, *args):
            if target.name == 'Netzelemente.csv': raise OSError('simulated write failure')
            return original(frame, target, *args)
        monkeypatch.setattr(contract, '_writeSingleCsv', fail)
    with pytest.raises(ConversionError, match='Failed to write MJAP'):
        runConversion(workbook, output, logger, mjapNetwork=True)
    assert {p.name:p.read_text() for p in output.iterdir()} == {name:'previous:'+name for name in names}


def testApiDoesNotAllowBothMjapModes(tmp_path, logger):
    with pytest.raises(ConversionError, match='either'):
        runConversion(tmp_path/'input.xlsx', tmp_path/'out', logger, mjap=True, mjapNetwork=True)


def testNetworkOnlyExportPreservesExistingCompanionFiles(tmp_path):
    workbook = writeExcel(rows(), tmp_path/'input.xlsx')
    output = tmp_path/'out'; output.mkdir()
    for name in ('Freischaltungen.csv', 'Projekte.csv'): (output/name).write_text('existing:'+name)
    assert main([str(workbook), '-o', str(output), '--no-color']) == 0
    for name in ('Freischaltungen.csv', 'Projekte.csv'): assert (output/name).read_text() == 'existing:'+name


@pytest.mark.parametrize('source', [rows, multipodRows])
def testDefaultNetworkCsvsAreByteIdenticalToVerifiedFullBundle(tmp_path, source, logger):
    workbook = writeExcel(source(), tmp_path/'input.xlsx')
    network, bundle = tmp_path/'network', tmp_path/'bundle'
    assert main([str(workbook), '-o', str(network), '--no-color']) == 0
    paths = companions(tmp_path)
    if source is multipodRows:
        outages = pd.read_csv(paths['outagesPath']); outages['Netzelement:MJAP-ID'] = 'Amprion_LINE_001'
        outages.to_csv(paths['outagesPath'], index=False)
        projects = pd.read_csv(paths['projectsPath']); projects['betroffener Standort'] = 'Amprion_StationA_380'
        projects.to_csv(paths['projectsPath'], index=False)
    runConversion(workbook, bundle, logger, mjap=True, **paths)
    for name in ('Stationen.csv', 'Netzelemente.csv'):
        assert (network/name).read_bytes() == (bundle/name).read_bytes()
