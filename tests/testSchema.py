import pytest

from cgmes2excel.mapping.schema import (
    NETZELEMENTE,
    NETZELEMENTE_COLUMNS,
    SHEETS,
    STATIONEN,
    STATIONEN_COLUMNS,
    SchemaViolation,
    ValueType,
    sheetByName,
)

EXPECTED_STATIONEN = [
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
]

EXPECTED_NETZELEMENTE = [
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
]


def testStationenSheetIsNamedExactly():
    assert STATIONEN.name == "Stationen"


def testNetzelementeSheetIsNamedExactly():
    assert NETZELEMENTE.name == "NETZELEMENTE"


def testStationenHasExactlyTwentyTwoColumns():
    assert len(STATIONEN_COLUMNS) == 22


def testNetzelementeHasExactlyTwentySevenColumns():
    assert len(NETZELEMENTE_COLUMNS) == 27


def testStationenColumnsMatchTheContractExactlyAndInOrder():
    assert list(STATIONEN_COLUMNS) == EXPECTED_STATIONEN


def testNetzelementeColumnsMatchTheContractExactlyAndInOrder():
    assert list(NETZELEMENTE_COLUMNS) == EXPECTED_NETZELEMENTE


def testColumnNamesAreCaseSensitiveAsContracted():
    assert "Stationname" in STATIONEN_COLUMNS
    assert "Stationsname" not in STATIONEN_COLUMNS
    assert "Element Typ" in NETZELEMENTE_COLUMNS
    assert "Elementtyp" in NETZELEMENTE_COLUMNS


def testBothSheetsAreExportedInOrder():
    assert [sheet.name for sheet in SHEETS] == ["Stationen", "NETZELEMENTE"]


def testSheetLookupByName():
    assert sheetByName("NETZELEMENTE") is NETZELEMENTE


def testUnknownSheetLookupRaises():
    with pytest.raises(KeyError):
        sheetByName("Tabelle1")


def testColumnsAreImmutable():
    with pytest.raises(AttributeError):
        STATIONEN_COLUMNS.append("Neu")


def testHeaderValidationAcceptsTheExactContract():
    assert STATIONEN.headerViolations(EXPECTED_STATIONEN) == []


def testHeaderValidationRejectsAReorderedHeader():
    reordered = EXPECTED_STATIONEN.copy()
    reordered[0], reordered[1] = reordered[1], reordered[0]
    violations = STATIONEN.headerViolations(reordered)
    assert violations
    assert "position 1" in violations[0]


def testHeaderValidationRejectsARenamedColumn():
    renamed = EXPECTED_NETZELEMENTE.copy()
    renamed[4] = "Elementtyp"
    violations = NETZELEMENTE.headerViolations(renamed)
    assert any("Element Typ" in violation for violation in violations)


def testHeaderValidationRejectsADifferentCapitalisation():
    recased = EXPECTED_STATIONEN.copy()
    recased[3] = "Lat"
    assert NETZELEMENTE.headerViolations(recased)
    assert STATIONEN.headerViolations(recased)


def testHeaderValidationRejectsAMissingColumn():
    violations = STATIONEN.headerViolations(EXPECTED_STATIONEN[:-1])
    assert any("22" in violation for violation in violations)


def testHeaderValidationRejectsAnExtraColumn():
    violations = STATIONEN.headerViolations([*EXPECTED_STATIONEN, "Extra"])
    assert any("23" in violation for violation in violations)


def testRowValidationRejectsAWrongWidth():
    with pytest.raises(SchemaViolation):
        STATIONEN.validateRowWidth(21)


def testLatitudeAndLongitudeAreNumericColumns():
    assert STATIONEN.valueTypeOf("lat") is ValueType.NUMBER
    assert STATIONEN.valueTypeOf("long") is ValueType.NUMBER


def testIdentifierColumnsAreTextSoTheyAreNeverCoercedToNumbers():
    for column in ("ID-GUID intern-1", "ID-OPC", "ID-UCTE", "ID", "MJAP-ID"):
        assert STATIONEN.valueTypeOf(column) is ValueType.TEXT


def testStationVoltageIsTextBecauseItMayCombineSeveralLevels():
    assert STATIONEN.valueTypeOf("Spannung") is ValueType.TEXT


def testNetworkElementVoltageIsNumericBecauseItIsASingleLevel():
    assert NETZELEMENTE.valueTypeOf("Spannung") is ValueType.NUMBER


def testColumnIndexIsOneBasedForSpreadsheetUse():
    assert STATIONEN.columnIndex("Eigentümer") == 1
    assert STATIONEN.columnIndex("Pfad") == 22
    assert NETZELEMENTE.columnIndex("Pfad") == 27
