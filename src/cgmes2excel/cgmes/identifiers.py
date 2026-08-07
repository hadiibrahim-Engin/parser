"""Normalization of CIM/RDF object identifiers.

CGMES serializations refer to the same object through several syntactic forms
(``rdf:ID="_x"``, ``rdf:about="#_x"``, ``rdf:resource="urn:uuid:x"``). A single
comparison key is needed so cross-profile references resolve, while the
original spelling must survive for output and diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass

_URN_UUID = "urn:uuid:"


def _bareValue(raw: str) -> str:
    value = raw.strip()
    if "#" in value:
        return value.rsplit("#", 1)[1]
    if value.lower().startswith(_URN_UUID):
        return value[len(_URN_UUID) :]
    return value


def normalizeId(raw: str | None) -> str:
    """Return the comparison key for any CIM identifier or reference form."""
    if not raw or not raw.strip():
        return ""
    return _bareValue(raw).lstrip("_").casefold()


@dataclass(frozen=True, slots=True)
class Identifier:
    """A CIM identifier that remembers how it was originally written."""

    raw: str
    key: str

    @classmethod
    def fromRaw(cls, raw: str | None) -> Identifier:
        return cls(raw=raw or "", key=normalizeId(raw))

    @property
    def mrid(self) -> str:
        """The identifier as a CGMES ``mRID``: no prefix, original casing."""
        return _bareValue(self.raw).lstrip("_")

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Identifier):
            return self.key == other.key
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.key)

    def __bool__(self) -> bool:
        return bool(self.key)

    def __str__(self) -> str:
        return self.mrid
