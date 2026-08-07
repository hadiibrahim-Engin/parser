"""Mapping of CGMES conducting equipment onto the ``NETZELEMENTE`` sheet.

Which classes become rows is decided by the equipment registry, not by this
module. How the four station columns are filled depends on the equipment
category, through a strategy table rather than a conditional chain:

* branch and switch equipment spans two stations -> Station Anfang / Station Ende
* transformers sit inside one station -> Station Anfang, plus Station T-1/T-2
  for the stations reached by winding ends 1 and 2
* singly connected equipment -> Station Anfang only

``Station T-1``/``Station T-2`` are interpreted as the transformer winding
stations. That reading is isolated here so it can be changed in one place if the
downstream contract turns out to mean something else.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ..cgmes.graph import CimObject
from ..diagnostics import Diagnostics
from ..domain.classification import ElementCategory, EquipmentRegistry
from ..domain.geography import GeographyResolver
from ..domain.network import NetworkModel
from ..domain.resolution import Resolution
from .rows import FieldRule, Row, RowBuilder, unavailable
from .schema import NETZELEMENTE

_NOT_IN_CGMES = "notRepresentedInCgmes"
_ORGANISATION_SPECIFIC = "organisationSpecificNotInCgmes"
_NOT_APPLICABLE = "notApplicableForThisEquipmentCategory"


@dataclass(slots=True)
class ElementContext:
    """Everything a network-element rule may consult."""

    equipment: CimObject
    category: ElementCategory
    model: NetworkModel
    geography: GeographyResolver
    _stations: dict[str, Resolution[str]] = field(default_factory=dict)

    def terminal(self, position: int) -> CimObject | None:
        return self.model.terminalAt(self.equipment, position)

    def substationAtTerminal(self, position: int) -> CimObject | None:
        terminal = self.terminal(position)
        return self.model.substationOfTerminal(terminal).value if terminal is not None else None

    def stationAtTerminal(self, position: int) -> Resolution[str]:
        terminal = self.terminal(position)
        if terminal is None:
            return Resolution.empty("noSuchTerminal", self.equipment.label())
        resolved = self.model.substationOfTerminal(terminal)
        if not resolved.found:
            return Resolution.empty(resolved.reason or "substationUnresolved", *resolved.trace)
        name = resolved.value.name or resolved.value.mrid
        return Resolution.of(name, *resolved.trace)

    def containingStation(self) -> Resolution[str]:
        resolved = self.model.substationOfEquipment(self.equipment)
        if resolved.found:
            name = resolved.value.name or resolved.value.mrid
            return Resolution.of(name, *resolved.trace)
        return self.stationAtTerminal(1)

    def stationRole(self, role: str) -> Resolution[str]:
        if role not in self._stations:
            self._stations[role] = _STATION_STRATEGIES[self.category][role](self)
        return self._stations[role]

    def nodeNameAtTerminal(self, position: int) -> Resolution[str]:
        terminal = self.terminal(position)
        if terminal is None:
            return Resolution.empty("noSuchTerminal", self.equipment.label())
        node = self.model.nodeOfTerminal(terminal)
        if not node.found:
            return Resolution.empty(node.reason or "terminalWithoutNode", *node.trace)
        name = node.value.name or node.value.mrid
        return Resolution.of(name, *node.trace)

    def lineContainer(self) -> CimObject | None:
        container = self.model.graph.follow(self.equipment, "Equipment.EquipmentContainer")
        return container if container is not None and container.cimClass == "Line" else None


def _notApplicable(_context: ElementContext) -> Resolution[str]:
    return Resolution.empty(_NOT_APPLICABLE)


_Strategy = Callable[[ElementContext], Resolution[str]]

_SPANNING_ROLES: dict[str, _Strategy] = {
    "anfang": lambda context: context.stationAtTerminal(1),
    "ende": lambda context: context.stationAtTerminal(2),
    "t1": _notApplicable,
    "t2": _notApplicable,
}

_TRANSFORMER_ROLES: dict[str, _Strategy] = {
    "anfang": lambda context: context.containingStation(),
    "ende": _notApplicable,
    "t1": lambda context: context.stationAtTerminal(1),
    "t2": lambda context: context.stationAtTerminal(2),
}

_SINGLE_ENDED_ROLES: dict[str, _Strategy] = {
    "anfang": lambda context: context.stationAtTerminal(1),
    "ende": _notApplicable,
    "t1": _notApplicable,
    "t2": _notApplicable,
}

_STATION_STRATEGIES: dict[ElementCategory, dict[str, _Strategy]] = {
    ElementCategory.BRANCH: _SPANNING_ROLES,
    ElementCategory.SWITCH: _SPANNING_ROLES,
    ElementCategory.TRANSFORMER: _TRANSFORMER_ROLES,
    ElementCategory.BUSBAR: _SINGLE_ENDED_ROLES,
    ElementCategory.INJECTION: _SINGLE_ENDED_ROLES,
    ElementCategory.OTHER: _SPANNING_ROLES,
}


def _circuitShortName(context: ElementContext) -> Resolution[str]:
    line = context.lineContainer()
    if line is not None:
        for label, value in (("shortName", line.shortName), ("name", line.name)):
            if value:
                return Resolution.of(value, line.label(), f"IdentifiedObject.{label}")
    equipment = context.equipment
    for label, value in (("shortName", equipment.shortName), ("name", equipment.name)):
        if value:
            return Resolution.of(value, equipment.label(), f"IdentifiedObject.{label}")
    return Resolution.empty("noCircuitName", equipment.label())


def _title(context: ElementContext) -> Resolution[str]:
    equipment = context.equipment
    for label, value in (("name", equipment.name), ("shortName", equipment.shortName)):
        if value:
            return Resolution.of(value, f"{equipment.cimClass} {equipment.mrid}", f"IdentifiedObject.{label}")
    return Resolution.empty("equipmentWithoutName", equipment.label())


def _elementType(context: ElementContext) -> Resolution[str]:
    return Resolution.of(context.equipment.cimClass, "CIM class of the source object")


def _voltage(context: ElementContext) -> Resolution[float]:
    return context.model.nominalVoltageOf(context.equipment)


def _mrid(context: ElementContext) -> Resolution[str]:
    return Resolution.of(context.equipment.mrid, context.equipment.cimClass, "IdentifiedObject.mRID")


def _comment(context: ElementContext) -> Resolution[str]:
    description = context.equipment.description
    if description:
        return Resolution.of(description, context.equipment.label(), "IdentifiedObject.description")
    return Resolution.empty("noDescription", context.equipment.label())


def _region(context: ElementContext) -> Resolution[str]:
    region = context.model.regionOf(context.equipment)
    if region.found:
        return region
    startStation = context.substationAtTerminal(1)
    if startStation is not None:
        viaStation = context.model.regionOf(startStation)
        if viaStation.found:
            return Resolution.of(viaStation.value, context.equipment.label(), *viaStation.trace)
    return Resolution.empty("noRegion", context.equipment.label())


def _path(context: ElementContext) -> Resolution[str]:
    path = context.model.pathOf(context.equipment)
    if not path:
        return Resolution.empty("noContainmentPath", context.equipment.label())
    return Resolution.of(path, "containment hierarchy")


def _station(role: str) -> Callable[[ElementContext], Resolution[str]]:
    return lambda context: context.stationRole(role)


def _node(position: int) -> Callable[[ElementContext], Resolution[str]]:
    return lambda context: context.nodeNameAtTerminal(position)


NETZELEMENTE_RULES: tuple[FieldRule[ElementContext], ...] = (
    unavailable("Eigentümer", _NOT_IN_CGMES, "Ownership is not carried by the exported CGMES profiles."),
    unavailable("MJAP-ID", _ORGANISATION_SPECIFIC, "Organisation-specific key with no CGMES counterpart."),
    FieldRule(
        "Stromkreisname - Kurzname",
        "shortName of the containing Line, falling back to its name, then to the equipment's own short name.",
        _circuitShortName,
    ),
    FieldRule("Title", "Equipment IdentifiedObject.name, falling back to shortName.", _title),
    FieldRule("Element Typ", "CIM class of the equipment, e.g. ACLineSegment.", _elementType),
    FieldRule(
        "Spannung",
        "ConductingEquipment.BaseVoltage, then the container VoltageLevel, then the TopologicalNode of terminal 1.",
        _voltage,
    ),
    unavailable("IBN", _NOT_IN_CGMES, "Commissioning date is not modelled in CGMES."),
    unavailable("ABN", _NOT_IN_CGMES, "Decommissioning date is not modelled in CGMES."),
    unavailable("relevant für", _ORGANISATION_SPECIFIC, "Organisation-specific classification."),
    FieldRule(
        "Station Anfang",
        "Substation of terminal 1 via topology; for transformers the containing substation.",
        _station("anfang"),
    ),
    FieldRule(
        "Station Ende",
        "Substation of terminal 2 via topology; empty for equipment that does not span two stations.",
        _station("ende"),
    ),
    FieldRule(
        "Station T-1",
        "Transformers only: substation reached by winding end 1.",
        _station("t1"),
    ),
    FieldRule(
        "Station T-2",
        "Transformers only: substation reached by winding end 2.",
        _station("t2"),
    ),
    FieldRule("Y-Knoten-1", "TopologicalNode of terminal 1, falling back to its ConnectivityNode.", _node(1)),
    FieldRule("Y-Knoten-2", "TopologicalNode of terminal 2, falling back to its ConnectivityNode.", _node(2)),
    unavailable("Stromkreisname - OPC-Name", _ORGANISATION_SPECIFIC, "Process-control naming lives outside CGMES."),
    FieldRule("ID-GUID intern-1", "Equipment IdentifiedObject.mRID.", _mrid),
    unavailable("ID-GUID intern-2", _ORGANISATION_SPECIFIC, "CGMES defines exactly one mRID per object."),
    unavailable("ID-OPC", _ORGANISATION_SPECIFIC, "Process-control identifier lives outside CGMES."),
    unavailable("ID-UCTE", _ORGANISATION_SPECIFIC, "No UCTE identifier is present in the export."),
    unavailable("ID", _ORGANISATION_SPECIFIC, "Identifier of the downstream system, not of CGMES."),
    FieldRule("Kommentar", "Equipment IdentifiedObject.description.", _comment),
    unavailable("Geändert", _NOT_IN_CGMES, "Per-object change timestamps are not part of CGMES."),
    unavailable("Geändert von", _NOT_IN_CGMES, "Per-object change authors are not part of CGMES."),
    FieldRule("Region", "SubGeographicalRegion reached from the equipment's container.", _region),
    FieldRule("Elementtyp", "CIM class of the source object.", _elementType),
    FieldRule("Pfad", "Containment path from the geographical region down to the equipment.", _path),
)

NETZELEMENTE_BUILDER: RowBuilder[ElementContext] = RowBuilder(NETZELEMENTE, NETZELEMENTE_RULES)


def elementObjects(model: NetworkModel, registry: EquipmentRegistry) -> list[CimObject]:
    """Every object whose CIM class is switched on in the registry."""
    found: list[CimObject] = []
    for cimClass in registry.includedClasses():
        found.extend(model.graph.byClass(cimClass))
    return found


def buildElementRows(
    model: NetworkModel,
    geography: GeographyResolver,
    registry: EquipmentRegistry,
    diagnostics: Diagnostics,
) -> list[Row]:
    rows: list[Row] = []
    for equipment in elementObjects(model, registry):
        kind = registry.kindFor(equipment.cimClass)
        _checkTerminals(model, equipment, kind.expectedTerminals, diagnostics)
        context = ElementContext(
            equipment=equipment,
            category=kind.category,
            model=model,
            geography=geography,
        )
        rows.append(NETZELEMENTE_BUILDER.build(context, diagnostics, sourceMrid=equipment.mrid))
    return rows


_TARGET_TERMINAL_COLUMNS = 2


def _checkTerminals(
    model: NetworkModel,
    equipment: CimObject,
    expected: int | None,
    diagnostics: Diagnostics,
) -> None:
    actual = len(model.terminalsOf(equipment))
    if expected is not None and actual != expected:
        diagnostics.warn(
            "unexpectedTerminalCount",
            "Equipment has an unexpected number of terminals",
            equipment=equipment.mrid,
            name=equipment.name or "",
            cimClass=equipment.cimClass,
            expected=expected,
            actual=actual,
        )
    if actual > _TARGET_TERMINAL_COLUMNS:
        # The sheet has two station and two node columns; further ends cannot be shown.
        diagnostics.warn(
            "terminalsBeyondTargetFormat",
            "Equipment has more terminals than the target sheet can represent; the surplus is not exported",
            equipment=equipment.mrid,
            name=equipment.name or "",
            cimClass=equipment.cimClass,
            terminals=actual,
            exported=_TARGET_TERMINAL_COLUMNS,
        )
