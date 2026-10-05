"""Isolated, real QGIS wizard probe; run by testMjapWizard.py."""
import gc
import json
import logging
import os
import sys
import warnings
import tempfile
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
root = Path(sys.argv[1])
scenario = sys.argv[2]
root.mkdir(parents=True, exist_ok=True)
reportPath = root / 'report.json'
root = Path(tempfile.mkdtemp(prefix=f'{scenario}-', dir=root))
os.environ['QGIS_CUSTOM_CONFIG_PATH'] = str(root / 'profile')
os.environ['MJAP_TPZW_SETTINGS_FILE'] = str(root / 'tpzw.ini')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, os.environ.get('NAHRIVA_WORKS', '/Users/hadi/Desktop/nahriva_works'))
from conftest import stationRow, elementRow, writeExcel
from excelToCsv.pipeline import runConversion
import pandas as pd
from qgis.core import (QgsApplication, QgsProject, QgsVectorLayer, QgsLayerTreeModel,
                       QgsExpression, QgsExpressionContext, QgsExpressionContextUtils,
                       QgsRuleBasedRenderer, Qgis)
from qgis.gui import QgsMessageBar, QgsLayerTreeView
from qgis.PyQt.QtWidgets import QMainWindow, QMenu, QFileDialog, QMessageBox
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt import sip
import qgis.utils

app = QgsApplication([], False)
app.setPrefixPath(sys.prefix, True)
app.initQgis()
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(root / 'profile'))
project = QgsProject.instance()
messages = []

class Bar(QgsMessageBar):
    def pushWarning(self, *args): messages.append(('warning', *args))
    def pushCritical(self, *args): messages.append(('critical', *args))
    def pushSuccess(self, *args): messages.append(('success', *args))

class Interface:
    def __init__(self):
        self.window = QMainWindow()
        self.menu = QMenu('Plugins', self.window)
        self.window.menuBar().addMenu(self.menu)
        self.tree = QgsLayerTreeView()
        self.model = QgsLayerTreeModel(project.layerTreeRoot())
        self.tree.setModel(self.model)
        self.bar = Bar()
    def mainWindow(self): return self.window
    def firstRightStandardMenu(self): return self.menu
    def layerTreeView(self): return self.tree
    def messageBar(self): return self.bar
    def registerOptionsWidgetFactory(self, *args): pass
    def unregisterOptionsWidgetFactory(self, *args): pass
    def addVectorLayer(self, path, name, provider):
        layer = QgsVectorLayer(path, name, provider)
        assert layer.isValid(), (name, path)
        project.addMapLayer(layer)
        return layer

interface = Interface()
qgis.utils.iface = interface
for kind in ('warning', 'critical', 'information'):
    setattr(QMessageBox, kind, staticmethod(lambda *args, k=kind, **kw:
        messages.append((k, str(args[1:3]))) or QMessageBox.Ok))
from mjap_plugin.plugin_main import MJAPPlugin

rows = [stationRow(), stationRow(**{'ELEMENT ID': 'Hamburg_380', 'Latitude': '53.55', 'Longitude': '9.99'}),
        elementRow(), elementRow(**{'ELEMENT ID': 'TRA_1', 'ELEMENT-TYPE': 'TRA'})]
if scenario == 'closed-lifetimes':
    for row in rows: row['ENDLIFETIME'] = '2035-12-31'
workbook = writeExcel(rows, root / 'network.xlsx')
outagesPath = projectsPath = None
if scenario in ('populated', 'closed-lifetimes', 'line-and-transformer'):
    outagesPath, projectsPath = root / 'outages.csv', root / 'projects.csv'
    pd.DataFrame([{'MJAP-ID': 'FS_1', 'Netzelement:MJAP-ID': 'Amprion_TRA_1',
                   'interne ID': 'FS_1', 'von': '01.06.2028', 'bis': '02.06.2028',
                   'Projekt': 'Demo', 'Maßnahme': 'IBN', 'Schaltungsart': 'gleichzeitig',
                   'Schaltung': 'Täglich'}]).to_csv(outagesPath, index=False)
    pd.DataFrame([{'Projektname': 'Demo', 'betroffener Standort': 'Amprion_Berlin_380,Amprion_Hamburg_380',
                   'Umsetzungzeitraum von': '01.01.2028', 'Umsetzungzeitraum bis': '31.12.2028'}]).to_csv(projectsPath, index=False)
    if scenario == 'line-and-transformer':
        outages = pd.read_csv(outagesPath)
        lineOutage = outages.iloc[0].copy()
        lineOutage['MJAP-ID'] = lineOutage['interne ID'] = 'FS_2'
        lineOutage['Netzelement:MJAP-ID'] = 'Amprion_LINE_471'
        lineOutage['Maßnahme'] = 'ABN'
        pd.concat([outages, pd.DataFrame([lineOutage])]).to_csv(outagesPath, index=False)
source, output = root / 'bundle', root / 'output'
output.mkdir()
runConversion(workbook, source, logging.getLogger('probe'), mjap=True,
              outagesPath=outagesPath, projectsPath=projectsPath)
plugin = MJAPPlugin(interface)
plugin.initGui()
directories = iter([str(source), str(output)])
QFileDialog.getExistingDirectory = staticmethod(lambda *args, **kw: next(directories))
with warnings.catch_warnings(record=True) as captured:
    warnings.simplefilter('always')
    plugin.wizard()

report = {'scenario': scenario, 'qgis': Qgis.QGIS_VERSION, 'pandas': pd.__version__,
          'messages': messages, 'warnings': [str(w.message) for w in captured],
          'layers': {}, 'expression_errors': []}
switches = 2 if scenario == 'line-and-transformer' else 1
expected = {'Standorte': 2, 'Stromkreise': 2, 'Standorte Schaltungen': 1,
            'Stromkreise Schaltungen': switches,
            'Standorte Projekte': 1, 'Stromkreise Projekte': switches}
for name, count in expected.items():
    layer = project.mapLayersByName(name)[0]
    assert layer.isValid() and layer.featureCount() == count, (name, layer.featureCount())
    for feature in layer.getFeatures():
        geometry = feature.geometry()
        assert not geometry.isEmpty() and geometry.isGeosValid(), name
        assert geometry.wkbType() == layer.wkbType(), name
    assert layer.temporalProperties().isActive(), name
    properties = layer.temporalProperties()
    assert properties.startField() in layer.fields().names(), (name, properties.startField())
    assert properties.endField() in layer.fields().names(), (name, properties.endField())
    report['layers'][name] = {'count': count, 'fields': layer.fields().names()}
    renderer = layer.renderer()
    if isinstance(renderer, QgsRuleBasedRenderer):
        def rules(rule):
            for child in rule.children():
                yield child
                yield from rules(child)
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.layerScope(layer))
        for rule in rules(renderer.rootRule()):
            expression = rule.filterExpression()
            if rule.active() and expression and expression != 'ELSE':
                compiled = QgsExpression(expression)
                if not compiled.prepare(context):
                    report['expression_errors'].append([name, expression, compiled.evalErrorString()])
attributes = pd.read_excel(output / 'attribute.xlsx', sheet_name=None)
assert set(attributes) == {'SO_Attribute', 'SK_Attribute', 'Schaltungen', 'Projekte'}
assert attributes['SK_Attribute']['MJAP-ID'].tolist() == ['Amprion_LINE_471', 'Amprion_TRA_1']
assert len(attributes['Schaltungen']) == switches
for name in ('Standorte', 'Stromkreise'):
    assert all(feature['Attribute_IBN'] for feature in project.mapLayersByName(name)[0].getFeatures())
assert all(feature['Standorte Projekte_Umsetzungzeitraum von']
           for feature in project.mapLayersByName('Stromkreise Projekte')[0].getFeatures())
assert all(frame.empty for frame in pd.read_excel(output / 'missing_data.xlsx', sheet_name=None).values())
assert project.write(str(output / 'Parser-MJAP.qgz'))
(root / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
reportPath.write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
plugin.unload()
project.clear()
qgis.utils.iface = None
for name, module in tuple(sys.modules.items()):
    if name.startswith('mjap_plugin.') and getattr(module, 'iface', None) is interface:
        module.iface = None
sip.delete(interface.tree)
sip.delete(interface.bar)
sip.delete(interface.window)
del layer, feature, renderer, plugin, interface
gc.collect()
app.exitQgis()
sip.delete(app)
