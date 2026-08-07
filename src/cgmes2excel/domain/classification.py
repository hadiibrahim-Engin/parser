"""Which CIM classes become NETZELEMENTE rows, and how each behaves.

A registry rather than a conditional chain: adding an equipment class is a
single registration, and callers select the included set at runtime.

The default included set is deliberately branch-oriented. The NETZELEMENTE
columns (Station Anfang/Ende, Station T-1/T-2, Y-Knoten-1/2) describe elements
that span two stations, so lines and transformers are exported by default while
switchgear, busbars and injections stay available but switched off.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class ElementCategory(Enum):
    BRANCH = "branch"
    TRANSFORMER = "transformer"
    SWITCH = "switch"
    BUSBAR = "busbar"
    INJECTION = "injection"
    OTHER = "other"


class UnknownEquipmentClassError(KeyError):
    """Raised when a CIM class has no registered behaviour."""


@dataclass(frozen=True, slots=True)
class EquipmentKind:
    """How one CIM equipment class is treated by the converter."""

    cimClass: str
    category: ElementCategory
    expectedTerminals: int | None
    includedByDefault: bool = False


_EXPECTED_TERMINALS = {
    ElementCategory.BRANCH: 2,
    ElementCategory.TRANSFORMER: None,  # two or three windings, both legitimate
    ElementCategory.SWITCH: 2,
    ElementCategory.BUSBAR: 1,
    ElementCategory.INJECTION: 1,
    ElementCategory.OTHER: None,
}


def _kind(cimClass: str, category: ElementCategory, includedByDefault: bool = False) -> EquipmentKind:
    return EquipmentKind(
        cimClass=cimClass,
        category=category,
        expectedTerminals=_EXPECTED_TERMINALS[category],
        includedByDefault=includedByDefault,
    )


_REGISTRATIONS: tuple[EquipmentKind, ...] = (
    _kind("ACLineSegment", ElementCategory.BRANCH, includedByDefault=True),
    _kind("DCLineSegment", ElementCategory.BRANCH, includedByDefault=True),
    _kind("SeriesCompensator", ElementCategory.BRANCH, includedByDefault=True),
    _kind("EquivalentBranch", ElementCategory.BRANCH, includedByDefault=True),
    _kind("PowerTransformer", ElementCategory.TRANSFORMER, includedByDefault=True),
    _kind("Breaker", ElementCategory.SWITCH),
    _kind("Disconnector", ElementCategory.SWITCH),
    _kind("LoadBreakSwitch", ElementCategory.SWITCH),
    _kind("GroundDisconnector", ElementCategory.SWITCH),
    _kind("Switch", ElementCategory.SWITCH),
    _kind("Fuse", ElementCategory.SWITCH),
    _kind("Jumper", ElementCategory.SWITCH),
    _kind("BusbarSection", ElementCategory.BUSBAR),
    _kind("EnergyConsumer", ElementCategory.INJECTION),
    _kind("ConformLoad", ElementCategory.INJECTION),
    _kind("NonConformLoad", ElementCategory.INJECTION),
    _kind("StationSupply", ElementCategory.INJECTION),
    _kind("SynchronousMachine", ElementCategory.INJECTION),
    _kind("AsynchronousMachine", ElementCategory.INJECTION),
    _kind("EnergySource", ElementCategory.INJECTION),
    _kind("EquivalentInjection", ElementCategory.INJECTION),
    _kind("LinearShuntCompensator", ElementCategory.INJECTION),
    _kind("NonlinearShuntCompensator", ElementCategory.INJECTION),
    _kind("StaticVarCompensator", ElementCategory.INJECTION),
    _kind("ExternalNetworkInjection", ElementCategory.INJECTION),
)

DEFAULT_ELEMENT_CLASSES: frozenset[str] = frozenset(
    kind.cimClass for kind in _REGISTRATIONS if kind.includedByDefault
)


class EquipmentRegistry:
    """Known equipment classes and the subset exported as network elements."""

    def __init__(self, kinds: dict[str, EquipmentKind], included: frozenset[str]) -> None:
        self._kinds = kinds
        self._included = included

    @classmethod
    def withDefaults(cls) -> EquipmentRegistry:
        return cls({kind.cimClass: kind for kind in _REGISTRATIONS}, DEFAULT_ELEMENT_CLASSES)

    def isKnown(self, cimClass: str) -> bool:
        return cimClass in self._kinds

    def isIncluded(self, cimClass: str) -> bool:
        return cimClass in self._included

    def kindFor(self, cimClass: str) -> EquipmentKind:
        try:
            return self._kinds[cimClass]
        except KeyError as exc:
            raise UnknownEquipmentClassError(cimClass) from exc

    def includedClasses(self) -> list[str]:
        return sorted(self._included)

    def knownClasses(self) -> list[str]:
        return sorted(self._kinds)

    def including(self, *cimClasses: str) -> EquipmentRegistry:
        """A copy that also exports ``cimClasses``, registering unknown ones."""
        return self._derive(self._included | frozenset(cimClasses), cimClasses)

    def onlyIncluding(self, *cimClasses: str) -> EquipmentRegistry:
        """A copy that exports exactly ``cimClasses``."""
        return self._derive(frozenset(cimClasses), cimClasses)

    def _derive(self, included: frozenset[str], newClasses: tuple[str, ...]) -> EquipmentRegistry:
        kinds = dict(self._kinds)
        for cimClass in newClasses:
            if cimClass not in kinds:
                kinds[cimClass] = _kind(cimClass, ElementCategory.OTHER)
        return EquipmentRegistry(kinds, included)

    def registering(self, kind: EquipmentKind) -> EquipmentRegistry:
        """A copy that knows about ``kind``, honouring its default inclusion."""
        kinds = dict(self._kinds) | {kind.cimClass: kind}
        included = self._included | ({kind.cimClass} if kind.includedByDefault else set())
        return EquipmentRegistry(kinds, frozenset(included))

    def withExpectedTerminals(self, cimClass: str, expected: int | None) -> EquipmentRegistry:
        return self.registering(replace(self.kindFor(cimClass), expectedTerminals=expected))
