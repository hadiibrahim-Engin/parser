"""Optional integration checks with the real, unchanged MJAP/QGIS modules.

Run in the neighboring MJAP project's QGIS environment. Normal parser test
environments without QGIS skip this module.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('qgis.core')
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer
from qgis.PyQt import sip
import qgis.utils
from conftest import elementRow, stationRow, writeExcel
from excelToCsv.pipeline import runConversion
from excelToCsv.errors import ConversionError
from excelToCsv.mapProject import addCountryMaps
from excelToCsv.cli import main
from excelToCsv.mjap import OUTAGE_COLUMNS, PROJECT_COLUMNS
from testMjap import rows as simpleRows
from testMultipod import multipodRows

WORKS = Path(os.environ.get('NAHRIVA_WORKS', '/Users/hadi/Desktop/nahriva_works'))


@pytest.fixture(scope='module')
def application(tmp_path_factory):
    os.environ['QGIS_CUSTOM_CONFIG_PATH'] = str(tmp_path_factory.mktemp('qgis-profile'))
    app = QgsApplication([], False)
    app.setPrefixPath(sys.prefix, True)
    app.initQgis()
    sys.path.insert(0, str(WORKS))
    bar = SimpleNamespace(pushWarning=lambda *args: None, pushSuccess=lambda *args: None)
    interface = SimpleNamespace(messageBar=lambda: bar)
    qgis.utils.iface = interface
    yield app
    QgsProject.instance().clear()
    for name, module in tuple(sys.modules.items()):
        if name.startswith('mjap_plugin.') and getattr(module, 'iface', None) is interface:
            module.iface = None
    qgis.utils.iface = None
    app.exitQgis()
    sip.delete(app)


@pytest.mark.parametrize('withOutages', [False, True])
def testGeneratedBundleRunsThroughRealMjap(application, tmp_path, logger, withOutages):
    from mjap_plugin.toolbelt.sharepoint2qgis_v4 import sharepoint2qgis
    rows = [stationRow(), stationRow(**{'ELEMENT ID': 'Hamburg_380', 'Latitude': '53.55', 'Longitude': '9.99'}),
            stationRow(**{'ELEMENT ID': 'XDemo_380', 'Latitude': '52.9', 'Longitude': '11.7'}),
            elementRow(**{'Station 1': 'XDemo_380'}),
            elementRow(**{'ELEMENT ID': 'TIE_1', 'ELEMENT-TYPE': 'TIE'})]
    workbook = writeExcel(rows, tmp_path / 'network.xlsx')
    outagesPath = projectsPath = None
    if withOutages:
        outagesPath = tmp_path / 'outages.csv'
        projectsPath = tmp_path / 'projects.csv'
        pd.DataFrame([{'MJAP-ID': 'FS_1', 'Netzelement:MJAP-ID': 'Amprion_TIE_1',
                       'interne ID': 'FS_1', 'von': '01.06.2028', 'bis': '02.06.2028',
                       'Projekt': 'Demo'}]).to_csv(outagesPath, index=False)
        pd.DataFrame([{'Projektname': 'Demo', 'betroffener Standort': 'Amprion_Berlin_380',
                       'Umsetzungzeitraum von': '01.01.2028', 'Umsetzungzeitraum bis': '31.12.2028'}]).to_csv(projectsPath, index=False)
    source, output = tmp_path / 'bundle', tmp_path / 'converted'
    output.mkdir()
    if not withOutages:
        with pytest.raises(ConversionError, match='header-only'):
            runConversion(workbook, source, logger, mjap=True)
        assert not source.exists()
        return
    runConversion(workbook, source, logger, mjap=True, outagesPath=outagesPath, projectsPath=projectsPath)
    sharepoint2qgis(str(source), str(output))
    assert len(pd.read_csv(output / 'SO.csv', sep=';')) == 3
    assert len(pd.read_csv(output / 'SK.csv', sep=';')) == 2
    attributes = pd.read_excel(output / 'attribute.xlsx', sheet_name=None)
    assert attributes['SK_Attribute']['IBN'].dt.strftime('%d.%m.%Y').tolist() == ['09.05.2025'] * 2
    assert attributes['SK_Attribute']['ABN'].isna().all()
    assert len(attributes['Schaltungen']) == int(withOutages)
    if withOutages:
        assert pd.isna(attributes['Schaltungen'].iloc[0]['Standort_von'])
    assert all(frame.empty for frame in pd.read_excel(output / 'missing_data.xlsx', sheet_name=None).values())


def testCountryMapsPreserveExistingLayersAndStayInEurope(application, tmp_path):
    project = QgsProject.instance()
    project.clear()
    existing = QgsVectorLayer('Point?crs=EPSG:4326', 'Existing MJAP layer', 'memory')
    project.addMapLayer(existing)
    original = existing.id()
    view = addCountryMaps(project, tmp_path, ['DE', 'NL', 'BE', 'FR'])
    assert project.mapLayer(original) is existing
    for code, name in [('DE', 'Deutschland'), ('NL', 'Niederlande'), ('BE', 'Belgien'), ('FR', 'Frankreich')]:
        layer = project.mapLayersByName(name)[0]
        assert layer.isValid() and layer.featureCount() == 1
        geometry = next(layer.getFeatures()).geometry()
        assert geometry.isGeosValid()
        assert layer.extent().yMinimum() > 40  # no overseas territories in overview
        assert next(layer.getFeatures())['country'] == code
    assert not view.isEmpty()
    assert project.write(str(tmp_path / 'countries.qgz'))
    # Repeating the operation replaces our group; it does not duplicate layers.
    addCountryMaps(project, tmp_path, ['NL', 'BE', 'FR'])
    assert len(project.mapLayers()) == 4
    assert project.mapLayer(original) is existing
    project.clear()
    del existing


@pytest.mark.parametrize('source, count', [(simpleRows, 2), (multipodRows, 5)])
def testSimpleExcelCommandSurvivesRealMjapShapeAndAttributeGeneration(application, tmp_path, source, count):
    from mjap_plugin.toolbelt.sharepoint2qgis_v4 import gen_shape_df, gen_multiple_commissionings, gen_attribute_df
    workbook = writeExcel(source(), tmp_path/'input.xlsx')
    output = tmp_path/'csv'
    assert main([str(workbook), '-o', str(output), '--details', '--no-color']) == 0
    stations = pd.read_csv(output/'Stationen.csv', decimal=',')
    elements = gen_multiple_commissionings(pd.read_csv(output/'Netzelemente.csv', decimal=','))
    so, sk = gen_shape_df(stations, elements)
    assert len(sk) == count and 'MJAP-ID' in sk.columns
    soAttrs, skAttrs, _, _ = gen_attribute_df(so, sk, elements, stations,
                                            pd.DataFrame(columns=OUTAGE_COLUMNS),
                                            pd.DataFrame(columns=PROJECT_COLUMNS))
    assert len(skAttrs) == count
    assert len(soAttrs) == len(stations)


def testLegacySpacesReproduceReportedMjapIdKeyError(application, tmp_path):
    from mjap_plugin.toolbelt.sharepoint2qgis_v4 import gen_shape_df, gen_multiple_commissionings, gen_attribute_df
    workbook = writeExcel(simpleRows(), tmp_path/'input.xlsx')
    output = tmp_path/'csv'
    assert main([str(workbook), '-o', str(output), '--legacy', '--no-color']) == 0
    stations = pd.read_csv(output/'Stationen.csv', decimal=',')
    elements = gen_multiple_commissionings(pd.read_csv(output/'Netzelemente.csv', decimal=','))
    so, sk = gen_shape_df(stations, elements)
    assert sk.empty and 'MJAP-ID' not in sk.columns
    with pytest.raises(KeyError, match='MJAP-ID'):
        gen_attribute_df(so, sk, elements, stations, pd.DataFrame(columns=OUTAGE_COLUMNS),
                         pd.DataFrame(columns=PROJECT_COLUMNS))


def testPartialExportSurvivesRealMjapWithoutLosingRetainedElements(application, tmp_path):
    from mjap_plugin.toolbelt.sharepoint2qgis_v4 import gen_shape_df, gen_multiple_commissionings, gen_attribute_df
    defective = [
        elementRow(**{'ELEMENT ID': 'BAD_DATE', 'STARTLIFETIME': 'invalid'}),
        stationRow(**{'ELEMENT ID': 'Pflege', 'Latitude': '50.0', 'Longitude': '8.0'}),
        elementRow(**{'ELEMENT ID': 'BAD_DEP', 'Station 2': 'Pflege'}),
    ]
    workbook = writeExcel(simpleRows() + multipodRows() + defective, tmp_path/'input.xlsx')
    output = tmp_path/'csv'
    assert main([str(workbook), '-o', str(output), '--no-color']) == 3
    stations = pd.read_csv(output/'Stationen.csv', decimal=',')
    elements = gen_multiple_commissionings(pd.read_csv(output/'Netzelemente.csv', decimal=','))
    so, sk = gen_shape_df(stations, elements)
    assert len(elements) == 5 and len(sk) == 7
    assert set(sk['MJAP-ID']) == set(elements['MJAP-ID'])
    _, attributes, _, _ = gen_attribute_df(so, sk, elements, stations,
        pd.DataFrame(columns=OUTAGE_COLUMNS), pd.DataFrame(columns=PROJECT_COLUMNS))
    assert len(attributes) == 7
