"""The indexed CIM object graph.

All documents of an export are loaded into one graph before any relationship is
followed. Objects are keyed by normalized identifier, so a reference resolves
regardless of which file its target lives in or when that file was read.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from ..diagnostics import Diagnostics
from .identifiers import Identifier
from .namespaces import isCimNamespace
from .reader import RawObject


def _isEnumerationValue(raw: str) -> bool:
    """Enumeration attributes are rdf:resource links into the CIM schema itself."""
    return "#" in raw and isCimNamespace(raw.rsplit("#", 1)[0] + "#")


@dataclass(slots=True)
class CimObject:
    """One CIM object, assembled from every profile that describes it."""

    identifier: Identifier
    cimClass: str
    classNamespace: str
    contributions: list[RawObject] = field(default_factory=list)
    diagnostics: Diagnostics | None = None

    def literal(self, name: str) -> str | None:
        for contribution in self.contributions:
            value = contribution.literal(name)
            if value is not None:
                return value
        return None

    def literals(self, name: str) -> list[str]:
        values: list[str] = []
        for contribution in self.contributions:
            values.extend(contribution.literals(name))
        return values

    def reference(self, name: str) -> Identifier | None:
        for contribution in self.contributions:
            value = contribution.reference(name)
            if value is not None:
                return value
        return None

    def references(self, name: str) -> list[Identifier]:
        values: list[Identifier] = []
        for contribution in self.contributions:
            values.extend(contribution.references(name))
        return values

    def enum(self, name: str) -> str | None:
        for contribution in self.contributions:
            value = contribution.enum(name)
            if value is not None:
                return value
        return None

    def number(self, name: str) -> float | None:
        raw = self.literal(name)
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            if self.diagnostics is not None:
                self.diagnostics.warn(
                    "invalidNumber",
                    f"Property {name} is not a number",
                    object=self.identifier.mrid,
                    cimClass=self.cimClass,
                    value=raw,
                )
            return None

    def integer(self, name: str) -> int | None:
        value = self.number(name)
        return None if value is None else int(value)

    @property
    def name(self) -> str | None:
        return self.literal("IdentifiedObject.name")

    @property
    def shortName(self) -> str | None:
        return self.literal("IdentifiedObject.shortName")

    @property
    def aliasName(self) -> str | None:
        return self.literal("IdentifiedObject.aliasName")

    @property
    def description(self) -> str | None:
        return self.literal("IdentifiedObject.description")

    @property
    def mrid(self) -> str:
        return self.literal("IdentifiedObject.mRID") or self.identifier.mrid

    @property
    def sources(self) -> list[str]:
        return [contribution.source.name for contribution in self.contributions]

    def label(self) -> str:
        """Short human-readable handle used in diagnostics."""
        return f"{self.cimClass} {self.name or self.mrid}"


class CimGraph:
    """Identifier index, class index and reverse-reference index over CIM objects."""

    def __init__(self, diagnostics: Diagnostics | None = None) -> None:
        self.diagnostics = diagnostics if diagnostics is not None else Diagnostics()
        self._byKey: dict[str, CimObject] = {}
        self._byClass: dict[str, list[CimObject]] = {}
        self._referrers: dict[tuple[str, str], list[CimObject]] = {}

    # -- population -----------------------------------------------------------

    def add(self, raw: RawObject | None) -> CimObject | None:
        if raw is None or not raw.identifier:
            return None
        existing = self._byKey.get(raw.identifier.key)
        obj = self._merge(existing, raw) if existing is not None else self._create(raw)
        self._indexReferences(obj, raw)
        return obj

    def _create(self, raw: RawObject) -> CimObject:
        obj = CimObject(
            identifier=raw.identifier,
            cimClass=raw.cimClass,
            classNamespace=raw.classNamespace,
            contributions=[raw],
            diagnostics=self.diagnostics,
        )
        self._byKey[raw.identifier.key] = obj
        self._byClass.setdefault(raw.cimClass, []).append(obj)
        return obj

    def _merge(self, obj: CimObject, raw: RawObject) -> CimObject:
        defining = [c for c in obj.contributions if not c.isAbout]
        if not raw.isAbout and defining:
            self.diagnostics.error(
                "duplicateIdentifier",
                "Identifier is defined more than once",
                identifier=raw.identifier.mrid,
                cimClass=raw.cimClass,
                first=defining[0].source.name,
                second=raw.source.name,
            )
        if raw.cimClass != obj.cimClass:
            self._reconcileClass(obj, raw)
        if not raw.isAbout and defining:
            obj.contributions.append(raw)
        elif not raw.isAbout:
            # The defining declaration is authoritative for conflicting literals.
            obj.contributions.insert(0, raw)
        else:
            obj.contributions.append(raw)
        return obj

    def _reconcileClass(self, obj: CimObject, raw: RawObject) -> None:
        self.diagnostics.warn(
            "conflictingClass",
            "Object is typed differently in different profiles",
            identifier=raw.identifier.mrid,
            first=obj.cimClass,
            second=raw.cimClass,
            document=raw.source.name,
        )
        if raw.isAbout:
            return
        self._byClass.get(obj.cimClass, []).remove(obj)
        obj.cimClass = raw.cimClass
        obj.classNamespace = raw.classNamespace
        self._byClass.setdefault(raw.cimClass, []).append(obj)

    def _indexReferences(self, obj: CimObject, raw: RawObject) -> None:
        for propertyName, targets in raw.referenceValues.items():
            for target in targets:
                if not target.key:
                    continue
                bucket = self._referrers.setdefault((target.key, propertyName), [])
                if obj not in bucket:
                    bucket.append(obj)

    # -- lookup ---------------------------------------------------------------

    def get(self, identifier: Identifier | str | None) -> CimObject | None:
        if identifier is None:
            return None
        key = identifier.key if isinstance(identifier, Identifier) else Identifier.fromRaw(identifier).key
        return self._byKey.get(key)

    def follow(self, source: CimObject | None, propertyName: str) -> CimObject | None:
        """Resolve ``source.propertyName``, reporting references that dangle."""
        if source is None:
            return None
        target = source.reference(propertyName)
        if target is None:
            return None
        resolved = self._byKey.get(target.key)
        if resolved is None:
            self.diagnostics.warn(
                "unresolvedReference",
                f"{propertyName} points at an object that is not in the export",
                source=source.identifier.mrid,
                sourceClass=source.cimClass,
                target=target.mrid,
            )
        return resolved

    def followAll(self, source: CimObject | None, propertyName: str) -> list[CimObject]:
        if source is None:
            return []
        resolved: list[CimObject] = []
        for target in source.references(propertyName):
            obj = self._byKey.get(target.key)
            if obj is None:
                self.diagnostics.warn(
                    "unresolvedReference",
                    f"{propertyName} points at an object that is not in the export",
                    source=source.identifier.mrid,
                    sourceClass=source.cimClass,
                    target=target.mrid,
                )
            else:
                resolved.append(obj)
        return resolved

    def byClass(self, cimClass: str) -> list[CimObject]:
        return list(self._byClass.get(cimClass, ()))

    def byClasses(self, cimClasses: object) -> list[CimObject]:
        found: list[CimObject] = []
        for cimClass in cimClasses:  # type: ignore[union-attr]
            found.extend(self._byClass.get(cimClass, ()))
        return found

    def referrers(self, target: CimObject | Identifier | None, propertyName: str) -> list[CimObject]:
        """Objects whose ``propertyName`` points at ``target``."""
        if target is None:
            return []
        key = target.identifier.key if isinstance(target, CimObject) else target.key
        return list(self._referrers.get((key, propertyName), ()))

    # -- integrity ------------------------------------------------------------

    def verifyReferences(self) -> int:
        """Report every reference whose target is missing; returns how many.

        Lazy resolution only notices a dangling reference when something
        follows it, and nothing follows the references of an object that is
        itself never reached. This sweep checks all of them once.
        """
        dangling = 0
        for obj in self._byKey.values():
            for contribution in obj.contributions:
                for propertyName, targets in contribution.referenceValues.items():
                    for target in targets:
                        if not target.key or _isEnumerationValue(target.raw):
                            continue
                        if target.key in self._byKey:
                            continue
                        dangling += 1
                        self.diagnostics.warn(
                            "unresolvedReference",
                            f"{propertyName} points at an object that is not in the export",
                            source=obj.identifier.mrid,
                            sourceClass=obj.cimClass,
                            target=target.mrid,
                            document=contribution.source.name,
                        )
        return dangling

    # -- aggregates -----------------------------------------------------------

    @property
    def objects(self) -> Iterator[CimObject]:
        return iter(self._byKey.values())

    def __len__(self) -> int:
        return len(self._byKey)

    def classCounts(self) -> dict[str, int]:
        return {cimClass: len(objects) for cimClass, objects in self._byClass.items() if objects}
