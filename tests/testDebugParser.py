"""The direct debug entry must run the real parser and preserve its failures."""
import pandas as pd
import pytest

import debug_parser
from conftest import elementRow, stationRow, writeExcel
from excelToCsv.errors import ConversionError


def configure(monkeypatch, workbook, output):
    monkeypatch.setattr(debug_parser, 'INPUT_XLSX', workbook)
    monkeypatch.setattr(debug_parser, 'OUTPUT_DIR', output)
    monkeypatch.setattr(debug_parser, 'DEBUG_LOG', output/'parser-debug.log')
    monkeypatch.setattr(debug_parser, 'PAUSE_AT_START', False)


def sourceRows():
    return [stationRow(), stationRow(**{'ELEMENT ID': 'Hamburg_380', 'Latitude': '53.55', 'Longitude': '9.99'}),
            elementRow(), elementRow(**{'ELEMENT ID': 'BAD', 'STARTLIFETIME': ''})]


def testConstantsDriveRealExcelConversionAndMaintenanceReports(tmp_path, monkeypatch):
    workbook = writeExcel(sourceRows(), tmp_path/'source.xlsx')
    original = workbook.read_bytes()
    output = tmp_path/'configured-output'
    configure(monkeypatch, workbook, output)
    result = debug_parser.run_debug()
    assert len(result.stations) == 2 and result.excludedRows == [5]
    assert pd.read_csv(output/'Netzelemente.csv')['MJAP-ID'].tolist() == ['Amprion_LINE_471']
    assert (output/'Fehlerliste.csv').exists() and (output/'Pflegebericht.html').exists()
    assert (output/'parser-debug.log').exists()
    assert workbook.read_bytes() == original


def testDirectDebugEntryExposesConversionErrorInsteadOfCliExitCode(tmp_path, monkeypatch):
    workbook = writeExcel(sourceRows(), tmp_path/'source.xlsx')
    output = tmp_path/'out'
    configure(monkeypatch, workbook, output)
    monkeypatch.setattr(debug_parser, 'STRICT', True)
    with pytest.raises(ConversionError, match='valid IBN'):
        debug_parser.run_debug()
    assert not (output/'Netzelemente.csv').exists()
    assert (output/'Pflegebericht.html').exists()
