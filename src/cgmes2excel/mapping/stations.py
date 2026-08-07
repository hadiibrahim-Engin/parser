"""Mapping of CGMES Substations onto the ``Stationen`` sheet.

One row per ``Substation``. A substation that spans several voltage levels
stays one row: ``Spannung`` lists its distinct nominal voltages highest first
(``380/110``) instead of splitting the station into several records.
"""

from __future__ import annotations

from dataclasses import dataclass

from cgmes2excel.cgmes.graph import CimObject
from cgmes2excel.diagnostics import Diagnostics
from cgmes2excel.domain.geography import GeographyResolver
from cgmes2excel.domain.network import NetworkModel
from cgmes2excel.domain.resolution import Resolution
from cgmes2excel.mapping.rows import FieldRule, Row, RowBuilder, unavailable
from cgmes2excel.mapping.schema import STATIONEN

_NOT_IN_CGMES = "notRepresentedInCgmes"
_ORGANISATION_SPECIFIC = "organisationSpecificNotInCgmes"


@dataclass(slots=True)
class StationContext:
    """Everything a station rule may consult."""

    substation: CimObject
    model: NetworkModel
    geography: GeographyResolver

    def coordinates(self) -> Resolution:
        return self.geography.coordinatesOf(self.substation)


def _name(context: StationContext) -> Resolution[str]:
    substation = context.substation
    for label, value in (
        ("IdentifiedObject.name", substation.name),
        ("IdentifiedObject.shortName", substation.shortName),
        ("IdentifiedObject.aliasName", substation.aliasName),
    ):
        if value:
            return Resolution.of(value, f"Substation {substation.mrid}", label)
    return Resolution.empty("substationWithoutName", f"Substation {substation.mrid}")


def _latitude(context: StationContext) -> Resolution[float]:
    coordinates = context.coordinates()
    if not coordinates.found:
        return Resolution.empty(coordinates.reason or "noCoordinates", *coordinates.trace)
    return Resolution.of(coordinates.value.latitude, *coordinates.trace, "yPosition")


def _longitude(context: StationContext) -> Resolution[float]:
    coordinates = context.coordinates()
    if not coordinates.found:
        return Resolution.empty(coordinates.reason or "noCoordinates", *coordinates.trace)
    return Resolution.of(coordinates.value.longitude, *coordinates.trace, "xPosition")


def _voltage(context: StationContext) -> Resolution[str]:
    voltages = context.model.nominalVoltagesOfSubstation(context.substation)
    if not voltages:
        return Resolution.empty("noVoltageLevelWithBaseVoltage", context.substation.label())
    rendered = "/".join(f"{value:g}" for value in voltages)
    return Resolution.of(rendered, context.substation.label(), f"{len(voltages)} voltage level(s)")


def _shortName(context: StationContext) -> Resolution[str]:
    substation = context.substation
    if substation.shortName:
        return Resolution.of(substation.shortName, substation.label(), "IdentifiedObject.shortName")
    if substation.aliasName:
        return Resolution.of(substation.aliasName, substation.label(), "IdentifiedObject.aliasName")
    return Resolution.empty("noShortName", substation.label())


def _mrid(context: StationContext) -> Resolution[str]:
    return Resolution.of(context.substation.mrid, "Substation", "IdentifiedObject.mRID")


def _comment(context: StationContext) -> Resolution[str]:
    description = context.substation.description
    if description:
        return Resolution.of(description, context.substation.label(), "IdentifiedObject.description")
    return Resolution.empty("noDescription", context.substation.label())


def _elementType(context: StationContext) -> Resolution[str]:
    return Resolution.of(context.substation.cimClass, "CIM class of the source object")


def _path(context: StationContext) -> Resolution[str]:
    path = context.model.pathOf(context.substation)
    if not path:
        return Resolution.empty("noContainmentPath", context.substation.label())
    return Resolution.of(path, "containment hierarchy")


STATIONEN_RULES: tuple[FieldRule[StationContext], ...] = (
    unavailable("Eigentümer", _NOT_IN_CGMES, "Ownership is not carried by the exported CGMES profiles."),
    unavailable("MJAP-ID", _ORGANISATION_SPECIFIC, "Organisation-specific key with no CGMES counterpart."),
    FieldRule("Stationname", "Substation IdentifiedObject.name, falling back to shortName then aliasName.", _name),
    FieldRule("lat", "GL PositionPoint.yPosition of the substation Location, WGS84 only.", _latitude),
    FieldRule("long", "GL PositionPoint.xPosition of the substation Location, WGS84 only.", _longitude),
    FieldRule(
        "Spannung",
        "Distinct BaseVoltage.nominalVoltage of the contained VoltageLevels, highest first, joined with '/'.",
        _voltage,
    ),
    unavailable("IBN", _NOT_IN_CGMES, "Commissioning date is not modelled in CGMES."),
    unavailable("ABN", _NOT_IN_CGMES, "Decommissioning date is not modelled in CGMES."),
    FieldRule(
        "Stationsname - Kurzname",
        "Substation IdentifiedObject.shortName, falling back to aliasName.",
        _shortName,
    ),
    unavailable("reales UW", _ORGANISATION_SPECIFIC, "Organisation-specific flag with no CGMES counterpart."),
    unavailable("Stationsname - OPC-Name", _ORGANISATION_SPECIFIC, "Process-control naming lives outside CGMES."),
    FieldRule("ID-GUID intern-1", "Substation IdentifiedObject.mRID.", _mrid),
    unavailable("ID-GUID intern-2", _ORGANISATION_SPECIFIC, "CGMES defines exactly one mRID per object."),
    unavailable("ID-OPC", _ORGANISATION_SPECIFIC, "Process-control identifier lives outside CGMES."),
    unavailable("ID-UCTE", _ORGANISATION_SPECIFIC, "No UCTE identifier is present in the export."),
    unavailable("relevant für", _ORGANISATION_SPECIFIC, "Organisation-specific classification."),
    unavailable("ID", _ORGANISATION_SPECIFIC, "Identifier of the downstream system, not of CGMES."),
    FieldRule("Kommentar", "Substation IdentifiedObject.description.", _comment),
    unavailable("Geändert", _NOT_IN_CGMES, "Per-object change timestamps are not part of CGMES."),
    unavailable("Geändert von", _NOT_IN_CGMES, "Per-object change authors are not part of CGMES."),
    FieldRule("Elementtyp", "CIM class of the source object, i.e. 'Substation'.", _elementType),
    FieldRule(
        "Pfad",
        "Containment path GeographicalRegion/SubGeographicalRegion/Substation.",
        _path,
    ),
)

STATIONEN_BUILDER: RowBuilder[StationContext] = RowBuilder(STATIONEN, STATIONEN_RULES)


def stationObjects(model: NetworkModel) -> list[CimObject]:
    """Every Substation in the model, in a stable order."""
    return model.graph.byClass("Substation")


def buildStationRows(
    model: NetworkModel,
    geography: GeographyResolver,
    diagnostics: Diagnostics,
) -> list[Row]:
    rows: list[Row] = []
    for substation in stationObjects(model):
        context = StationContext(substation=substation, model=model, geography=geography)
        rows.append(STATIONEN_BUILDER.build(context, diagnostics, sourceMrid=substation.mrid))
    return rows
