"""Add offline country maps to a QGIS project without modifying MJAP.

Run with the QGIS Python environment, after the MJAP visualization wizard.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
COUNTRIES = {'DE': 'Deutschland', 'NL': 'Niederlande', 'BE': 'Belgien', 'FR': 'Frankreich'}
SOURCE = Path(__file__).resolve().parent / 'maps' / 'countries-europe.geojson'
GROUP = 'Länder und Hintergrund'


def addCountryMaps(project, outputDir: Path, countries: list[str], osm: bool = False):
    from qgis.core import (QgsVectorLayer, QgsVectorFileWriter, QgsGeometry, QgsRectangle,
                           QgsProject, QgsFillSymbol, QgsRasterLayer, QgsCoordinateReferenceSystem,
                           QgsCoordinateTransform, QgsReferencedRectangle, QgsPalLayerSettings,
                           QgsVectorLayerSimpleLabeling, QgsTextFormat)
    from qgis.PyQt.QtGui import QColor

    if not countries or len(countries) != len(set(countries)):
        raise ValueError('Select at least one country, without duplicates.')
    if set(countries) - set(COUNTRIES):
        raise ValueError('Supported map countries: ' + ', '.join(COUNTRIES))
    source = QgsVectorLayer(str(SOURCE), 'Natural Earth source', 'ogr')
    if not source.isValid():
        raise RuntimeError(f'Cannot read country map data: {SOURCE}')
    outputDir.mkdir(parents=True, exist_ok=True)
    root = project.layerTreeRoot()
    old = root.findGroup(GROUP)
    if old:
        for node in old.findLayers():
            project.removeMapLayer(node.layerId())
        root.removeChildNode(old)
    group = root.addGroup(GROUP)
    gpkg = outputDir / 'Laender.gpkg'
    wgs84 = QgsCoordinateReferenceSystem('EPSG:4326')
    # European map view only: overseas territories are outside this overview.
    europe = QgsGeometry.fromRect(QgsRectangle(-12, 34, 19, 58))
    combined = QgsRectangle()
    colors = {'DE': '#edf0f4', 'NL': '#fff0d9', 'BE': '#e8f2e9', 'FR': '#e8f0fa'}
    for index, code in enumerate(countries):
        memory = QgsVectorLayer('MultiPolygon?crs=EPSG:4326', COUNTRIES[code], 'memory')
        memory.dataProvider().addAttributes(source.fields())
        memory.updateFields()
        for feature in source.getFeatures():
            if feature['country'] != code:
                continue
            geometry = feature.geometry().intersection(europe)
            if geometry.isEmpty():
                raise RuntimeError(f'No European geometry for {code}')
            geometry.convertToMultiType()
            feature.setGeometry(geometry)
            if not memory.dataProvider().addFeature(feature):
                raise RuntimeError(f'Cannot add country geometry for {code}')
        memory.updateExtents()
        if memory.featureCount() != 1:
            raise RuntimeError(f'Expected exactly one country record for {code}')
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = 'GPKG'
        options.layerName = code
        options.actionOnExistingFile = (QgsVectorFileWriter.CreateOrOverwriteFile if index == 0
                                        else QgsVectorFileWriter.CreateOrOverwriteLayer)
        result = QgsVectorFileWriter.writeAsVectorFormatV3(memory, str(gpkg), project.transformContext(), options)
        if result[0] != QgsVectorFileWriter.NoError:
            raise RuntimeError(f'Cannot write country map: {result}')
        layer = QgsVectorLayer(f'{gpkg}|layername={code}', COUNTRIES[code], 'ogr')
        if not layer.isValid():
            raise RuntimeError(f'Cannot load country map for {code}')
        symbol = QgsFillSymbol.createSimple({'color': colors[code] if not osm else '255,255,255,0',
                                             'outline_color': '#65758b', 'outline_width': '0.35'})
        layer.renderer().setSymbol(symbol)
        labels = QgsPalLayerSettings()
        labels.fieldName = 'name'
        text = QgsTextFormat()
        text.setSize(11)
        text.setColor(QColor('#374151'))
        labels.setFormat(text)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(labels))
        layer.setLabelsEnabled(True)
        metadata = layer.metadata()
        metadata.setTitle(COUNTRIES[code] + ' – Natural Earth 1:50m')
        metadata.setAbstract('Natural Earth v5.1.2, Public Domain. European overview; overseas territories excluded.')
        layer.setMetadata(metadata)
        layer.setCustomProperty('mjap/background', True)
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        combined.combineExtentWith(layer.extent())
    if osm:
        raster = QgsRasterLayer('type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmin=0&zmax=19',
                                'OpenStreetMap · © OpenStreetMap contributors', 'wms')
        if not raster.isValid():
            raise RuntimeError('Cannot initialize the OpenStreetMap XYZ layer.')
        project.addMapLayer(raster, False)
        group.addLayer(raster)
    destination = QgsCoordinateReferenceSystem('EPSG:3857')
    project.setCrs(destination)
    view = QgsCoordinateTransform(wgs84, destination, project).transformBoundingBox(combined)
    view.scale(1.06)
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(view, destination))
    attribution = 'Ländergrenzen: Natural Earth v5.1.2 (Public Domain)'
    if osm:
        attribution += ' · © OpenStreetMap contributors · https://www.openstreetmap.org/copyright'
    project.writeEntry('CopyrightLabel', '/Enabled', True)
    project.writeEntry('CopyrightLabel', '/Label', attribution)
    project.writeEntry('CopyrightLabel', '/Placement', 3)
    project.writeEntry('CopyrightLabel', '/MarginH', 8)
    project.writeEntry('CopyrightLabel', '/MarginV', 8)
    return view


def renderOverview(project, view, path: Path):
    from qgis.core import QgsMapSettings, QgsMapRendererParallelJob
    from qgis.PyQt.QtCore import QSize
    from qgis.PyQt.QtGui import QColor, QPainter
    settings = QgsMapSettings()
    settings.setDestinationCrs(project.crs())
    settings.setTransformContext(project.transformContext())
    settings.setLayers(project.layerTreeRoot().layerOrder())
    settings.setExtent(view)
    settings.setOutputSize(QSize(1400, 1000))
    settings.setBackgroundColor(QColor('#fafbfc'))
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    if job.errors():
        raise RuntimeError(str(job.errors()))
    image = job.renderedImage()
    painter = QPainter(image)
    painter.setPen(QColor('#374151'))
    painter.drawText(14, image.height() - 14, 'Ländergrenzen: Natural Earth v5.1.2 (Public Domain)')
    painter.end()
    if not image.save(str(path)):
        raise RuntimeError(f'Cannot save map preview: {path}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, help='Existing MJAP .qgs/.qgz project; optional for an empty map.')
    parser.add_argument('--output', type=Path, required=True, help='New output .qgz project.')
    parser.add_argument('--countries', nargs='+', default=list(COUNTRIES), choices=list(COUNTRIES))
    parser.add_argument('--osm', action='store_true', help='Add online OpenStreetMap tiles; offline borders are always included.')
    parser.add_argument('--preview', type=Path, help='Render an offline PNG overview; cannot combine with --osm.')
    args = parser.parse_args(argv)
    if args.preview and args.osm:
        parser.error('Use --preview without --osm; online tiles are loaded interactively in QGIS.')
    if args.project and args.project.resolve() == args.output.resolve():
        parser.error('Choose a different output filename to preserve the existing project.')
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    os.environ.setdefault('QGIS_CUSTOM_CONFIG_PATH', str(args.output.parent / '.qgis-map-profile'))
    from qgis.core import QgsApplication, QgsProject
    app = QgsApplication([], False)
    QgsApplication.setPrefixPath(sys.prefix, True)
    app.initQgis()
    project = QgsProject.instance()
    try:
        if args.project and not project.read(str(args.project)):
            raise RuntimeError(f'Cannot open existing project: {args.project}')
        view = addCountryMaps(project, args.output.parent, args.countries, args.osm)
        if not project.write(str(args.output)):
            raise RuntimeError(f'Cannot write map project: {args.output}')
        if args.preview:
            renderOverview(project, view, args.preview)
        print(json.dumps({'project': str(args.output), 'countries': args.countries,
                          'online_basemap': args.osm, 'status': 'passed'}))
    finally:
        project.clear()
        app.exitQgis()
        from qgis.PyQt import sip
        sip.delete(app)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
