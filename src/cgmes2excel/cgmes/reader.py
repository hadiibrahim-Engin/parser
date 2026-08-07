"""Streaming RDF/XML reader for CGMES documents.

Reads one document into flat :class:`RawObject` records without resolving any
reference. Resolution is the graph layer's job; keeping the two apart is what
makes file order and profile order irrelevant.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from .identifiers import Identifier
from .namespaces import RDF_ABOUT, RDF_ID, RDF_RESOURCE, splitTag


class MalformedDocumentError(Exception):
    """Raised when a document is not well-formed XML."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"{path}: {reason}")
        self.path = path
        self.reason = reason


@dataclass(slots=True)
class RawObject:
    """One RDF description: a typed node with literal and reference properties."""

    identifier: Identifier
    cimClass: str
    classNamespace: str
    source: Path
    documentOrder: int
    isAbout: bool
    literalValues: dict[str, list[str]] = field(default_factory=dict)
    referenceValues: dict[str, list[Identifier]] = field(default_factory=dict)

    def literal(self, name: str) -> str | None:
        values = self.literalValues.get(name)
        return values[0] if values else None

    def literals(self, name: str) -> list[str]:
        return list(self.literalValues.get(name, ()))

    def reference(self, name: str) -> Identifier | None:
        values = self.referenceValues.get(name)
        return values[0] if values else None

    def references(self, name: str) -> list[Identifier]:
        return list(self.referenceValues.get(name, ()))

    def enum(self, name: str) -> str | None:
        """Value of an enumeration attribute, e.g. ``WindingConnection.D`` -> ``D``."""
        ref = self.reference(name)
        if ref is None:
            return None
        return ref.raw.rsplit("#", 1)[-1].rsplit(".", 1)[-1] or None

    @property
    def propertyNames(self) -> list[str]:
        return sorted({*self.literalValues, *self.referenceValues})

    def addLiteral(self, name: str, value: str) -> None:
        self.literalValues.setdefault(name, []).append(value)

    def addReference(self, name: str, value: Identifier) -> None:
        self.referenceValues.setdefault(name, []).append(value)


@dataclass(slots=True)
class DocumentStats:
    """Counts collected while reading a single document."""

    objects: int = 0
    anonymous: int = 0


def readRdfXml(path: Path, stats: DocumentStats | None = None) -> Iterator[RawObject]:
    """Yield every identified RDF description in ``path``, in document order."""
    with open(path, "rb") as stream:
        yield from readRdfXmlStream(stream, path, stats)


def readRdfXmlStream(
    stream: object,
    displayPath: Path,
    stats: DocumentStats | None = None,
) -> Iterator[RawObject]:
    """Parse RDF/XML from any binary stream, attributing objects to ``displayPath``."""
    path = displayPath
    stats = stats if stats is not None else DocumentStats()
    order = 0
    current: RawObject | None = None
    depth = 0
    try:
        for event, element in ElementTree.iterparse(stream, events=("start", "end")):  # type: ignore[arg-type]
            if event == "start":
                depth += 1
                if depth == 2:
                    current = _startObject(element, path, order, stats)
                    order += 1
                continue

            depth -= 1
            if depth == 2 and current is not None:
                _applyProperty(current, element)
            elif depth == 1:
                if current is not None:
                    yield current
                current = None
                element.clear()
    except ElementTree.ParseError as exc:
        raise MalformedDocumentError(path, str(exc)) from exc


def _startObject(element, path: Path, order: int, stats: DocumentStats) -> RawObject | None:
    rawId = element.get(RDF_ID)
    raw = rawId or element.get(RDF_ABOUT)
    if not raw:
        stats.anonymous += 1
        return None
    namespace, local = splitTag(element.tag)
    stats.objects += 1
    return RawObject(
        identifier=Identifier.fromRaw(raw),
        cimClass=local,
        classNamespace=namespace,
        source=path,
        documentOrder=order,
        isAbout=rawId is None,
    )


def _applyProperty(obj: RawObject, element) -> None:
    _, local = splitTag(element.tag)
    resource = element.get(RDF_RESOURCE)
    if resource is not None:
        obj.addReference(local, Identifier.fromRaw(resource))
        return
    text = (element.text or "").strip()
    if text:
        obj.addLiteral(local, text)
