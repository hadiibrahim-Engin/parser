"""The target workbook contract.

Sheet names, column names, capitalization and column order are consumed by a
downstream process and must never change. They are declared here once, and the
written workbook is validated against these declarations before a run is
considered successful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ValueType(Enum):
    """How a cell must be written so its meaning survives the round trip."""

    TEXT = "text"
    NUMBER = "number"


class SchemaViolation(Exception):
    """Raised when output would break the agreed workbook contract."""


STATIONEN_COLUMNS: tuple[str, ...] = (
    "Eigentümer",
    "MJAP-ID",
    "Stationname",
    "lat",
    "long",
    "Spannung",
    "IBN",
    "ABN",
    "Stationsname - Kurzname",
    "reales UW",
    "Stationsname - OPC-Name",
    "ID-GUID intern-1",
    "ID-GUID intern-2",
    "ID-OPC",
    "ID-UCTE",
    "relevant für",
    "ID",
    "Kommentar",
    "Geändert",
    "Geändert von",
    "Elementtyp",
    "Pfad",
)

NETZELEMENTE_COLUMNS: tuple[str, ...] = (
    "Eigentümer",
    "MJAP-ID",
    "Stromkreisname - Kurzname",
    "Title",
    "Element Typ",
    "Spannung",
    "IBN",
    "ABN",
    "relevant für",
    "Station Anfang",
    "Station Ende",
    "Station T-1",
    "Station T-2",
    "Y-Knoten-1",
    "Y-Knoten-2",
    "Stromkreisname - OPC-Name",
    "ID-GUID intern-1",
    "ID-GUID intern-2",
    "ID-OPC",
    "ID-UCTE",
    "ID",
    "Kommentar",
    "Geändert",
    "Geändert von",
    "Region",
    "Elementtyp",
    "Pfad",
)


@dataclass(frozen=True, slots=True)
class SheetSchema:
    """One worksheet of the contract."""

    name: str
    columns: tuple[str, ...]
    numericColumns: frozenset[str] = field(default_factory=frozenset)

    @property
    def width(self) -> int:
        return len(self.columns)

    def columnIndex(self, column: str) -> int:
        """One-based column position, as spreadsheets count."""
        return self.columns.index(column) + 1

    def valueTypeOf(self, column: str) -> ValueType:
        return ValueType.NUMBER if column in self.numericColumns else ValueType.TEXT

    def headerViolations(self, header: list[str]) -> list[str]:
        """Every way ``header`` deviates from the contract."""
        violations: list[str] = []
        if len(header) != self.width:
            violations.append(
                f"{self.name}: expected {self.width} columns, found {len(header)}"
            )
        for index, expected in enumerate(self.columns):
            actual = header[index] if index < len(header) else None
            if actual != expected:
                violations.append(
                    f"{self.name}: column at position {index + 1} must be {expected!r}, found {actual!r}"
                )
        return violations

    def validateRowWidth(self, width: int) -> None:
        if width != self.width:
            raise SchemaViolation(f"{self.name}: a row has {width} cells, expected {self.width}")


STATIONEN = SheetSchema(
    name="Stationen",
    columns=STATIONEN_COLUMNS,
    # A station may span several voltage levels, so Spannung stays text.
    numericColumns=frozenset({"lat", "long"}),
)

NETZELEMENTE = SheetSchema(
    name="NETZELEMENTE",
    columns=NETZELEMENTE_COLUMNS,
    numericColumns=frozenset({"Spannung"}),
)

SHEETS: tuple[SheetSchema, ...] = (STATIONEN, NETZELEMENTE)


def sheetByName(name: str) -> SheetSchema:
    for sheet in SHEETS:
        if sheet.name == name:
            return sheet
    raise KeyError(name)
