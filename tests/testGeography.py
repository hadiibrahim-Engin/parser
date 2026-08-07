import cgmesFixtures as fx
from cgmes2excel.cgmes.identifiers import Identifier
from cgmes2excel.diagnostics import Diagnostics
from cgmes2excel.domain.geography import (
    Coordinates,
    GeographyResolver,
    isWgs84,
)


def resolverFor(tmpPath, documents, diagnostics=None):
    diagnostics = diagnostics or Diagnostics()
    graph = fx.graphFrom(tmpPath, documents, diagnostics)
    return GeographyResolver(graph, diagnostics), graph


def find(graph, mrid):
    return graph.get(Identifier.fromRaw(mrid))


# --- coordinate reference systems --------------------------------------------


def testEpsg4326UrnIsRecognisedAsWgs84():
    assert isWgs84("urn:ogc:def:crs:EPSG::4326")
    assert isWgs84("urn:ogc:def:crs:EPSG:4326")


def testCrs84AndWgs84SpellingsAreRecognised():
    assert isWgs84("urn:ogc:def:crs:OGC:1.3:CRS84")
    assert isWgs84("EPSG:4326")
    assert isWgs84("WGS84")


def testProjectedCoordinateSystemsAreNotTreatedAsWgs84():
    assert not isWgs84("urn:ogc:def:crs:EPSG::25832")
    assert not isWgs84("urn:ogc:def:crs:EPSG::3857")


def testUnknownCrsIsNotAssumedToBeWgs84():
    assert not isWgs84("")
    assert not isWgs84(None)


# --- resolution --------------------------------------------------------------


def testSubstationCoordinatesAreResolvedThroughLocationAndPositionPoint(tmp_path):
    resolver, graph = resolverFor(tmp_path, {"eq.xml": fx.sampleEquipment(), "gl.xml": fx.sampleGeography()})
    result = resolver.coordinatesOf(find(graph, "_SUBA"))
    assert result.value == Coordinates(latitude=53.551086, longitude=9.993682)


def testXPositionIsLongitudeAndYPositionIsLatitudeUnderWgs84(tmp_path):
    resolver, graph = resolverFor(tmp_path, {"eq.xml": fx.sampleEquipment(), "gl.xml": fx.sampleGeography()})
    coordinates = resolver.coordinatesOf(find(graph, "_SUBB")).value
    assert coordinates.longitude == 10.686389
    assert coordinates.latitude == 53.866667


def testLocationReferencedFromThePowerSystemResourceSideAlsoResolves(tmp_path):
    body = "".join(
        [
            fx.obj("Substation", "S", fx.named("S"), fx.ref("PowerSystemResource.Location", "LOC")),
            fx.obj("CoordinateSystem", "CRS", fx.prop("CoordinateSystem.crsUrn", "urn:ogc:def:crs:EPSG::4326")),
            fx.obj("Location", "LOC", fx.ref("Location.CoordinateSystem", "CRS")),
            fx.obj("PositionPoint", "PP", fx.prop("PositionPoint.xPosition", "7.1"), fx.prop("PositionPoint.yPosition", "51.2"), fx.ref("PositionPoint.Location", "LOC")),
        ]
    )
    resolver, graph = resolverFor(tmp_path, {"all.xml": body})
    assert resolver.coordinatesOf(find(graph, "_S")).value == Coordinates(latitude=51.2, longitude=7.1)


def testFirstPositionPointBySequenceNumberIsUsed(tmp_path):
    body = "".join(
        [
            fx.obj("Substation", "S", fx.named("S")),
            fx.obj("CoordinateSystem", "CRS", fx.prop("CoordinateSystem.crsUrn", "urn:ogc:def:crs:EPSG::4326")),
            fx.obj("Location", "LOC", fx.ref("Location.CoordinateSystem", "CRS"), fx.ref("Location.PowerSystemResources", "S")),
            fx.obj("PositionPoint", "P2", fx.prop("PositionPoint.sequenceNumber", "2"), fx.prop("PositionPoint.xPosition", "8.0"), fx.prop("PositionPoint.yPosition", "52.0"), fx.ref("PositionPoint.Location", "LOC")),
            fx.obj("PositionPoint", "P1", fx.prop("PositionPoint.sequenceNumber", "1"), fx.prop("PositionPoint.xPosition", "7.0"), fx.prop("PositionPoint.yPosition", "51.0"), fx.ref("PositionPoint.Location", "LOC")),
        ]
    )
    resolver, graph = resolverFor(tmp_path, {"all.xml": body})
    assert resolver.coordinatesOf(find(graph, "_S")).value == Coordinates(latitude=51.0, longitude=7.0)


def testMultiplePositionPointsAreReportedAsAnOutline(tmp_path):
    body = "".join(
        [
            fx.obj("Substation", "S", fx.named("Weitläufig")),
            fx.obj("CoordinateSystem", "CRS", fx.prop("CoordinateSystem.crsUrn", "urn:ogc:def:crs:EPSG::4326")),
            fx.obj("Location", "LOC", fx.ref("Location.CoordinateSystem", "CRS"), fx.ref("Location.PowerSystemResources", "S")),
            fx.obj("PositionPoint", "P1", fx.prop("PositionPoint.sequenceNumber", "1"), fx.prop("PositionPoint.xPosition", "7.0"), fx.prop("PositionPoint.yPosition", "51.0"), fx.ref("PositionPoint.Location", "LOC")),
            fx.obj("PositionPoint", "P2", fx.prop("PositionPoint.sequenceNumber", "2"), fx.prop("PositionPoint.xPosition", "8.0"), fx.prop("PositionPoint.yPosition", "52.0"), fx.ref("PositionPoint.Location", "LOC")),
        ]
    )
    diag = Diagnostics()
    resolver, graph = resolverFor(tmp_path, {"all.xml": body}, diag)
    resolver.coordinatesOf(find(graph, "_S"))
    assert "locationIsAnOutline" in diag.countByCode()


# --- refusals ----------------------------------------------------------------


def testProjectedCoordinatesAreRefusedRatherThanMislabelledAsLatLong(tmp_path):
    body = "".join(
        [
            fx.obj("Substation", "S", fx.named("S")),
            fx.obj("CoordinateSystem", "CRS", fx.prop("CoordinateSystem.crsUrn", "urn:ogc:def:crs:EPSG::25832")),
            fx.obj("Location", "LOC", fx.ref("Location.CoordinateSystem", "CRS"), fx.ref("Location.PowerSystemResources", "S")),
            fx.obj("PositionPoint", "PP", fx.prop("PositionPoint.xPosition", "556000"), fx.prop("PositionPoint.yPosition", "5934000"), fx.ref("PositionPoint.Location", "LOC")),
        ]
    )
    diag = Diagnostics()
    resolver, graph = resolverFor(tmp_path, {"all.xml": body}, diag)
    result = resolver.coordinatesOf(find(graph, "_S"))
    assert not result.found
    assert result.reason == "unsupportedCoordinateSystem"
    assert "unsupportedCoordinateSystem" in diag.countByCode()


def testMissingCoordinateSystemIsAssumedWgs84AndAnnounced(tmp_path):
    body = "".join(
        [
            fx.obj("Substation", "S", fx.named("S")),
            fx.obj("Location", "LOC", fx.ref("Location.PowerSystemResources", "S")),
            fx.obj("PositionPoint", "PP", fx.prop("PositionPoint.xPosition", "7.0"), fx.prop("PositionPoint.yPosition", "51.0"), fx.ref("PositionPoint.Location", "LOC")),
        ]
    )
    diag = Diagnostics()
    resolver, graph = resolverFor(tmp_path, {"all.xml": body}, diag)
    result = resolver.coordinatesOf(find(graph, "_S"))
    assert result.value == Coordinates(latitude=51.0, longitude=7.0)
    assert "assumedCoordinateSystem" in diag.countByCode()


def testSubstationWithoutALocationYieldsNoCoordinates(tmp_path):
    resolver, graph = resolverFor(tmp_path, {"eq.xml": fx.sampleEquipment()})
    result = resolver.coordinatesOf(find(graph, "_SUBA"))
    assert not result.found
    assert result.reason == "noLocation"


def testLocationWithoutPositionPointsYieldsNoCoordinates(tmp_path):
    body = "".join(
        [
            fx.obj("Substation", "S", fx.named("S")),
            fx.obj("Location", "LOC", fx.ref("Location.PowerSystemResources", "S")),
        ]
    )
    diag = Diagnostics()
    resolver, graph = resolverFor(tmp_path, {"all.xml": body}, diag)
    result = resolver.coordinatesOf(find(graph, "_S"))
    assert not result.found
    assert result.reason == "locationWithoutPositionPoints"


def testUnparseablePositionIsReportedAndSkipped(tmp_path):
    body = "".join(
        [
            fx.obj("Substation", "S", fx.named("S")),
            fx.obj("Location", "LOC", fx.ref("Location.PowerSystemResources", "S")),
            fx.obj("PositionPoint", "PP", fx.prop("PositionPoint.xPosition", "east"), fx.prop("PositionPoint.yPosition", "north"), fx.ref("PositionPoint.Location", "LOC")),
        ]
    )
    diag = Diagnostics()
    resolver, graph = resolverFor(tmp_path, {"all.xml": body}, diag)
    assert not resolver.coordinatesOf(find(graph, "_S")).found
    assert "invalidPositionPoint" in diag.countByCode()


def testOutOfRangeCoordinatesAreRejected(tmp_path):
    body = "".join(
        [
            fx.obj("Substation", "S", fx.named("S")),
            fx.obj("Location", "LOC", fx.ref("Location.PowerSystemResources", "S")),
            fx.obj("PositionPoint", "PP", fx.prop("PositionPoint.xPosition", "556000"), fx.prop("PositionPoint.yPosition", "5934000"), fx.ref("PositionPoint.Location", "LOC")),
        ]
    )
    diag = Diagnostics()
    resolver, graph = resolverFor(tmp_path, {"all.xml": body}, diag)
    result = resolver.coordinatesOf(find(graph, "_S"))
    assert not result.found
    assert "coordinatesOutOfRange" in diag.countByCode()


def testResolutionRecordsHowTheCoordinatesWereReached(tmp_path):
    resolver, graph = resolverFor(tmp_path, {"eq.xml": fx.sampleEquipment(), "gl.xml": fx.sampleGeography()})
    trace = resolver.coordinatesOf(find(graph, "_SUBA")).describe()
    assert "Location" in trace
    assert "PositionPoint" in trace


def testCoordinatesAreCachedPerPowerSystemResource(tmp_path):
    resolver, graph = resolverFor(tmp_path, {"eq.xml": fx.sampleEquipment(), "gl.xml": fx.sampleGeography()})
    substation = find(graph, "_SUBA")
    assert resolver.coordinatesOf(substation) is resolver.coordinatesOf(substation)
