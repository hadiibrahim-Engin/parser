"""Semantic traversal of the CIM network model.

This is the single place where CIM relationships are interpreted. Mapping rules
ask questions here ("which substation is this terminal in?") and never walk the
graph themselves, so the traversal logic exists exactly once.
"""

from __future__ import annotations

from ..cgmes.graph import CimGraph, CimObject
from ..diagnostics import Diagnostics
from .resolution import Resolution

# Containment associations, keyed by the class that declares them.
_PARENT_PROPERTIES: tuple[str, ...] = (
    "Substation.Region",
    "SubGeographicalRegion.Region",
    "VoltageLevel.Substation",
    "Bay.VoltageLevel",
    "Line.Region",
    "Equipment.EquipmentContainer",
)

_NODE_CONTAINER_PROPERTIES = (
    "TopologicalNode.ConnectivityNodeContainer",
    "ConnectivityNode.ConnectivityNodeContainer",
)

_TERMINAL_NODE_PROPERTIES = ("Terminal.TopologicalNode", "Terminal.ConnectivityNode")

_SEQUENCE_PROPERTIES = ("ACDCTerminal.sequenceNumber", "Terminal.sequenceNumber")

_REGION_PROPERTIES = ("Substation.Region", "Line.Region", "Equipment.EquipmentContainer")

_MAX_CONTAINER_DEPTH = 12


class NetworkModel:
    """Answers semantic questions about an indexed CGMES model."""

    def __init__(self, graph: CimGraph, diagnostics: Diagnostics) -> None:
        self.graph = graph
        self.diagnostics = diagnostics
        self._cache: dict[tuple[str, str], object] = {}

    def _cached[T](self, kind: str, obj: CimObject, compute) -> T:
        key = (kind, obj.identifier.key)
        if key not in self._cache:
            self._cache[key] = compute()
        return self._cache[key]  # type: ignore[return-value]

    # -- terminals ------------------------------------------------------------

    def terminalsOf(self, equipment: CimObject | None) -> list[CimObject]:
        """Terminals of ``equipment``, in semantic order (end/sequence number)."""
        if equipment is None:
            return []
        return self._cached("terminals", equipment, lambda: self._orderTerminals(equipment))

    def _orderTerminals(self, equipment: CimObject) -> list[CimObject]:
        terminals = self.graph.referrers(equipment, "Terminal.ConductingEquipment")
        if not terminals:
            self.diagnostics.warn(
                "equipmentWithoutTerminals",
                "Conducting equipment has no terminals",
                equipment=equipment.mrid,
                cimClass=equipment.cimClass,
                name=equipment.name or "",
            )
            return []
        if len(terminals) == 1:
            return terminals

        byEndNumber = self._transformerEndOrder(equipment, terminals)
        if byEndNumber is not None:
            return byEndNumber
        bySequence = self._sequenceOrder(terminals)
        if bySequence is not None:
            return bySequence

        self.diagnostics.warn(
            "terminalOrderUndetermined",
            "Terminal order is not defined by the model; document order was used",
            equipment=equipment.mrid,
            cimClass=equipment.cimClass,
            name=equipment.name or "",
            terminals=len(terminals),
        )
        return sorted(terminals, key=self._documentPosition)

    def _transformerEndOrder(self, equipment: CimObject, terminals: list[CimObject]) -> list[CimObject] | None:
        ends = self.graph.referrers(equipment, "PowerTransformerEnd.PowerTransformer")
        if not ends:
            return None
        numbers: dict[str, int] = {}
        for end in ends:
            terminal = self.graph.follow(end, "TransformerEnd.Terminal")
            endNumber = end.integer("TransformerEnd.endNumber")
            if terminal is None or endNumber is None:
                return None
            numbers[terminal.identifier.key] = endNumber
        if len(set(numbers.values())) != len(terminals):
            return None
        if any(terminal.identifier.key not in numbers for terminal in terminals):
            return None
        return sorted(terminals, key=lambda t: numbers[t.identifier.key])

    def _sequenceOrder(self, terminals: list[CimObject]) -> list[CimObject] | None:
        numbers: list[int] = []
        for terminal in terminals:
            value = next(
                (n for name in _SEQUENCE_PROPERTIES if (n := terminal.integer(name)) is not None),
                None,
            )
            if value is None:
                return None
            numbers.append(value)
        if len(set(numbers)) != len(numbers):
            return None
        return [terminal for _, terminal in sorted(zip(numbers, terminals), key=lambda pair: pair[0])]

    @staticmethod
    def _documentPosition(terminal: CimObject) -> tuple[str, int]:
        first = terminal.contributions[0]
        return (first.source.name, first.documentOrder)

    def terminalAt(self, equipment: CimObject | None, position: int) -> CimObject | None:
        """The ``position``-th terminal (1-based) of ``equipment``, if it exists."""
        terminals = self.terminalsOf(equipment)
        return terminals[position - 1] if 0 < position <= len(terminals) else None

    # -- nodes ----------------------------------------------------------------

    def nodeOfTerminal(self, terminal: CimObject | None) -> Resolution[CimObject]:
        """The topological node of a terminal, or its connectivity node."""
        if terminal is None:
            return Resolution.empty("noTerminal")
        return self._cached("node", terminal, lambda: self._resolveNode(terminal))

    def _resolveNode(self, terminal: CimObject) -> Resolution[CimObject]:
        step = f"Terminal {terminal.name or terminal.mrid}"
        for propertyName in _TERMINAL_NODE_PROPERTIES:
            node = self.graph.follow(terminal, propertyName)
            if node is not None:
                return Resolution.of(node, step, node.label())
        return Resolution.empty("terminalWithoutNode", step)

    def containerOfNode(self, node: CimObject | None) -> CimObject | None:
        if node is None:
            return None
        for propertyName in _NODE_CONTAINER_PROPERTIES:
            container = self.graph.follow(node, propertyName)
            if container is not None:
                return container
        return None

    def terminalsOnNode(self, node: CimObject | None) -> list[CimObject]:
        """Every terminal attached to ``node``, through topology or connectivity."""
        if node is None:
            return []
        found: list[CimObject] = []
        for propertyName in _TERMINAL_NODE_PROPERTIES:
            for terminal in self.graph.referrers(node, propertyName):
                if terminal not in found:
                    found.append(terminal)
        return found

    # -- containment ----------------------------------------------------------

    def parentOf(self, obj: CimObject | None) -> CimObject | None:
        """The containing object one level up the CIM containment hierarchy."""
        if obj is None:
            return None
        for propertyName in _PARENT_PROPERTIES:
            if obj.reference(propertyName) is not None:
                return self.graph.follow(obj, propertyName)
        return None

    def voltageLevelOfContainer(self, container: CimObject | None) -> CimObject | None:
        current = container
        for _ in range(_MAX_CONTAINER_DEPTH):
            if current is None:
                return None
            if current.cimClass == "VoltageLevel":
                return current
            if current.cimClass == "Bay":
                current = self.graph.follow(current, "Bay.VoltageLevel")
                continue
            return None
        return None

    def substationOfContainer(self, container: CimObject | None) -> Resolution[CimObject]:
        current = container
        steps: list[str] = []
        for _ in range(_MAX_CONTAINER_DEPTH):
            if current is None:
                return Resolution.empty("noContainer", *steps)
            steps.append(current.label())
            if current.cimClass == "Substation":
                return Resolution.of(current, *steps)
            if current.cimClass == "VoltageLevel":
                current = self.graph.follow(current, "VoltageLevel.Substation")
                continue
            if current.cimClass == "Bay":
                current = self.graph.follow(current, "Bay.VoltageLevel")
                continue
            # Line, EquivalentNetwork and similar containers are not in a station.
            return Resolution.empty("containerIsNotInASubstation", *steps)
        return Resolution.empty("containerCycle", *steps)

    def substationOfEquipment(self, equipment: CimObject | None) -> Resolution[CimObject]:
        """The substation that contains ``equipment`` by CIM containment alone."""
        if equipment is None:
            return Resolution.empty("noEquipment")
        return self._cached("substationOfEquipment", equipment, lambda: self._resolveEquipmentSubstation(equipment))

    def _resolveEquipmentSubstation(self, equipment: CimObject) -> Resolution[CimObject]:
        container = self.graph.follow(equipment, "Equipment.EquipmentContainer")
        if container is None:
            return Resolution.empty("noEquipmentContainer", equipment.label())
        return self.substationOfContainer(container).then()

    def voltageLevelOfEquipment(self, equipment: CimObject | None) -> CimObject | None:
        if equipment is None:
            return None
        return self.voltageLevelOfContainer(self.graph.follow(equipment, "Equipment.EquipmentContainer"))

    def voltageLevelOfTerminal(self, terminal: CimObject | None) -> Resolution[CimObject]:
        """The voltage level a terminal sits in, via its node's container."""
        node = self.nodeOfTerminal(terminal)
        if not node.found:
            return Resolution.empty(node.reason or "noNode", *node.trace)
        container = self.containerOfNode(node.value)
        voltageLevel = self.voltageLevelOfContainer(container)
        if voltageLevel is None:
            reason = "nodeWithoutContainer" if container is None else "nodeNotInAVoltageLevel"
            return Resolution.empty(reason, *node.trace)
        return Resolution.of(voltageLevel, *node.trace, voltageLevel.label())

    def substationOfTerminal(self, terminal: CimObject | None) -> Resolution[CimObject]:
        """The substation a terminal belongs to, through topology or connectivity."""
        if terminal is None:
            return Resolution.empty("noTerminal")
        return self._cached("substationOfTerminal", terminal, lambda: self._resolveTerminalSubstation(terminal))

    def _resolveTerminalSubstation(self, terminal: CimObject) -> Resolution[CimObject]:
        voltageLevel = self.voltageLevelOfTerminal(terminal)
        if voltageLevel.found:
            substation = self.graph.follow(voltageLevel.value, "VoltageLevel.Substation")
            if substation is not None:
                return Resolution.of(substation, *voltageLevel.trace, substation.label())
            return Resolution.empty("voltageLevelWithoutSubstation", *voltageLevel.trace)

        viaNeighbour = self._substationViaNeighbouringTerminals(terminal)
        if viaNeighbour.found:
            return viaNeighbour

        equipment = self.graph.follow(terminal, "Terminal.ConductingEquipment")
        byContainment = self.substationOfEquipment(equipment)
        if byContainment.found:
            return Resolution.of(byContainment.value, f"Terminal {terminal.name or terminal.mrid}", *byContainment.trace)
        return Resolution.empty(voltageLevel.reason or "substationUnresolved", *voltageLevel.trace)

    def _substationViaNeighbouringTerminals(self, terminal: CimObject) -> Resolution[CimObject]:
        """Boundary case: the node lives in a Line, so ask the equipment sharing it."""
        node = self.nodeOfTerminal(terminal)
        if not node.found:
            return Resolution.empty("terminalWithoutNode")
        for sibling in self.terminalsOnNode(node.value):
            if sibling.identifier == terminal.identifier:
                continue
            equipment = self.graph.follow(sibling, "Terminal.ConductingEquipment")
            substation = self.substationOfEquipment(equipment)
            if substation.found:
                return Resolution.of(
                    substation.value,
                    f"Terminal {terminal.name or terminal.mrid}",
                    node.value.label(),
                    f"shared with {sibling.label()}",
                    *substation.trace,
                )
        return Resolution.empty("noNeighbourInASubstation")

    # -- voltage --------------------------------------------------------------

    def nominalVoltageOfBaseVoltage(self, baseVoltage: CimObject | None) -> float | None:
        return None if baseVoltage is None else baseVoltage.number("BaseVoltage.nominalVoltage")

    def nominalVoltageOf(self, equipment: CimObject | None) -> Resolution[float]:
        """Nominal voltage of equipment: own BaseVoltage, then container, then node."""
        if equipment is None:
            return Resolution.empty("noEquipment")
        return self._cached("nominalVoltage", equipment, lambda: self._resolveNominalVoltage(equipment))

    def _resolveNominalVoltage(self, equipment: CimObject) -> Resolution[float]:
        direct = self.graph.follow(equipment, "ConductingEquipment.BaseVoltage")
        voltage = self.nominalVoltageOfBaseVoltage(direct)
        if voltage is not None:
            return Resolution.of(voltage, equipment.label(), direct.label())

        voltageLevel = self.voltageLevelOfEquipment(equipment)
        if voltageLevel is not None:
            baseVoltage = self.graph.follow(voltageLevel, "VoltageLevel.BaseVoltage")
            voltage = self.nominalVoltageOfBaseVoltage(baseVoltage)
            if voltage is not None:
                return Resolution.of(voltage, equipment.label(), voltageLevel.label(), baseVoltage.label())

        terminal = self.terminalAt(equipment, 1)
        node = self.nodeOfTerminal(terminal)
        if node.found:
            baseVoltage = self.graph.follow(node.value, "TopologicalNode.BaseVoltage")
            voltage = self.nominalVoltageOfBaseVoltage(baseVoltage)
            if voltage is not None:
                return Resolution.of(voltage, equipment.label(), *node.trace, baseVoltage.label())

        return Resolution.empty("noBaseVoltage", equipment.label())

    def voltageLevelsOfSubstation(self, substation: CimObject | None) -> list[CimObject]:
        return self.graph.referrers(substation, "VoltageLevel.Substation")

    def nominalVoltagesOfSubstation(self, substation: CimObject | None) -> list[float]:
        """Distinct nominal voltages of a substation, highest first."""
        if substation is None:
            return []
        return self._cached("substationVoltages", substation, lambda: self._resolveSubstationVoltages(substation))

    def _resolveSubstationVoltages(self, substation: CimObject) -> list[float]:
        voltageLevels = self.voltageLevelsOfSubstation(substation)
        if not voltageLevels:
            self.diagnostics.warn(
                "substationWithoutVoltageLevel",
                "Substation contains no voltage level",
                substation=substation.mrid,
                name=substation.name or "",
            )
            return []

        voltages: list[float] = []
        for voltageLevel in voltageLevels:
            baseVoltage = self.graph.follow(voltageLevel, "VoltageLevel.BaseVoltage")
            voltage = self.nominalVoltageOfBaseVoltage(baseVoltage)
            if voltage is None:
                self.diagnostics.warn(
                    "voltageLevelWithoutBaseVoltage",
                    "Voltage level has no usable BaseVoltage",
                    voltageLevel=voltageLevel.mrid,
                    name=voltageLevel.name or "",
                    substation=substation.name or substation.mrid,
                )
                continue
            if voltage not in voltages:
                voltages.append(voltage)

        voltages.sort(reverse=True)
        if len(voltages) > 1:
            self.diagnostics.warn(
                "multiVoltageSubstation",
                "Substation spans several voltage levels",
                substation=substation.name or substation.mrid,
                voltages=", ".join(f"{value:g} kV" for value in voltages),
            )
        return voltages

    # -- regions and paths ----------------------------------------------------

    def regionOf(self, obj: CimObject | None) -> Resolution[str]:
        """Name of the sub-geographical region an object belongs to."""
        if obj is None:
            return Resolution.empty("noObject")
        return self._cached("region", obj, lambda: self._resolveRegion(obj))

    def _resolveRegion(self, obj: CimObject) -> Resolution[str]:
        for propertyName in _REGION_PROPERTIES:
            target = self.graph.follow(obj, propertyName)
            if target is None:
                continue
            if target.cimClass == "SubGeographicalRegion":
                name = target.name
                if name:
                    return Resolution.of(name, obj.label(), target.label())
            else:
                inherited = self.regionOf(target)
                if inherited.found:
                    return Resolution.of(inherited.value, obj.label(), *inherited.trace)
        return Resolution.empty("noRegion", obj.label())

    def pathOf(self, obj: CimObject | None) -> str:
        """Slash-separated containment path, outermost container first."""
        if obj is None:
            return ""
        return self._cached("path", obj, lambda: self._resolvePath(obj))

    def _resolvePath(self, obj: CimObject) -> str:
        segments: list[str] = []
        seen: set[str] = set()
        current: CimObject | None = obj
        while current is not None and current.identifier.key not in seen:
            seen.add(current.identifier.key)
            segments.append(current.name or current.mrid)
            current = self.parentOf(current)
        return "/".join(reversed(segments))
