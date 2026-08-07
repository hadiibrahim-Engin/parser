"""Geographic coordinates from the GL profile.

``xPosition``/``yPosition`` only mean longitude/latitude in a geographic CRS.
This module refuses to emit lat/long for projected systems rather than shipping
plausible-looking but wrong numbers downstream.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from cgmes2excel.cgmes.graph import CimGraph, CimObject
from cgmes2excel.diagnostics import Diagnostics
from cgmes2excel.domain.resolution import Resolution

_WGS84_PATTERNS = (
    re.compile(r"epsg:{1,2}4326\b", re.IGNORECASE),
    re.compile(r"\bcrs84\b", re.IGNORECASE),
    re.compile(r"\bwgs[\s_-]?84\b", re.IGNORECASE),
)

_LOCATION_FROM_RESOURCE = "PowerSystemResource.Location"
_RESOURCE_FROM_LOCATION = "Location.PowerSystemResources"


@dataclass(frozen=True, slots=True)
class Coordinates:
    """A WGS84 position in degrees."""

    latitude: float
    longitude: float


def isWgs84(crsUrn: str | None) -> bool:
    """Whether a ``CoordinateSystem.crsUrn`` denotes WGS84 lat/long degrees."""
    if not crsUrn:
        return False
    return any(pattern.search(crsUrn) for pattern in _WGS84_PATTERNS)


def _inDegreeRange(latitude: float, longitude: float) -> bool:
    return -90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0


class GeographyResolver:
    """Resolves a power system resource to WGS84 coordinates."""

    def __init__(self, graph: CimGraph, diagnostics: Diagnostics) -> None:
        self.graph = graph
        self.diagnostics = diagnostics
        self._cache: dict[str, Resolution[Coordinates]] = {}

    def coordinatesOf(self, resource: CimObject | None) -> Resolution[Coordinates]:
        if resource is None:
            return Resolution.empty("noResource")
        key = resource.identifier.key
        if key not in self._cache:
            self._cache[key] = self._resolve(resource)
        return self._cache[key]

    def locationOf(self, resource: CimObject) -> CimObject | None:
        """The GL Location of a resource, from either side of the association."""
        forward = self.graph.follow(resource, _LOCATION_FROM_RESOURCE)
        if forward is not None:
            return forward
        reverse = self.graph.referrers(resource, _RESOURCE_FROM_LOCATION)
        return reverse[0] if reverse else None

    def positionPointsOf(self, location: CimObject) -> list[CimObject]:
        """Position points of a location, ordered by their sequence number."""
        points = self.graph.referrers(location, "PositionPoint.Location")
        return sorted(points, key=lambda point: (point.integer("PositionPoint.sequenceNumber") or 0))

    def _resolve(self, resource: CimObject) -> Resolution[Coordinates]:
        location = self.locationOf(resource)
        if location is None:
            return Resolution.empty("noLocation", resource.label())

        steps = [resource.label(), location.label()]
        points = self.positionPointsOf(location)
        if not points:
            self.diagnostics.warn(
                "locationWithoutPositionPoints",
                "GL location carries no position point",
                resource=resource.mrid,
                name=resource.name or "",
                location=location.mrid,
            )
            return Resolution.empty("locationWithoutPositionPoints", *steps)

        if len(points) > 1:
            self.diagnostics.info(
                "locationIsAnOutline",
                "Location has several position points; the first one is used",
                resource=resource.name or resource.mrid,
                points=len(points),
            )

        crs = self.graph.follow(location, "Location.CoordinateSystem")
        crsUrn = crs.literal("CoordinateSystem.crsUrn") if crs is not None else None
        if crsUrn is None:
            self.diagnostics.info(
                "assumedCoordinateSystem",
                "No coordinate system on the location; WGS84 assumed as the GL profile prescribes",
                resource=resource.name or resource.mrid,
                location=location.mrid,
            )
        elif not isWgs84(crsUrn):
            self.diagnostics.warn(
                "unsupportedCoordinateSystem",
                "Coordinates are not WGS84 and were left empty rather than mislabelled",
                resource=resource.name or resource.mrid,
                crs=crsUrn,
            )
            return Resolution.empty("unsupportedCoordinateSystem", *steps)

        point = points[0]
        longitude = point.number("PositionPoint.xPosition")
        latitude = point.number("PositionPoint.yPosition")
        if longitude is None or latitude is None:
            self.diagnostics.warn(
                "invalidPositionPoint",
                "Position point has no usable x/y value",
                resource=resource.name or resource.mrid,
                point=point.mrid,
                x=point.literal("PositionPoint.xPosition") or "",
                y=point.literal("PositionPoint.yPosition") or "",
            )
            return Resolution.empty("invalidPositionPoint", *steps)

        if not _inDegreeRange(latitude, longitude):
            self.diagnostics.warn(
                "coordinatesOutOfRange",
                "Position is outside the WGS84 degree range; the coordinate system is probably projected",
                resource=resource.name or resource.mrid,
                point=point.mrid,
                x=f"{longitude:g}",
                y=f"{latitude:g}",
            )
            return Resolution.empty("coordinatesOutOfRange", *steps)

        return Resolution.of(Coordinates(latitude=latitude, longitude=longitude), *steps, point.label())
