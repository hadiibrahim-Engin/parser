"""Unit Tests der reinen Normalisierungsfunktionen."""

from __future__ import annotations

import datetime as dt

import pytest

from excelToCsv.errors import NormalizationError
from excelToCsv.normalize import (
    isVirtualStation,
    normalizeCoordinate,
    normalizeDate,
    normalizeElementType,
    normalizeLatitude,
    normalizeLongitude,
    normalizeText,
    normalizeVoltage,
    parseBoolean,
    splitStationId,
    splitVoltages,
)


# --------------------------------------------------------------------------- #
# Spannung (Fall 6, 7)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("380.0", "380"),
        ("110.0", "110"),
        (380.0, "380"),
        (380, "380"),
        ("380", "380"),
        ("0.4", "0.4"),
        ("  220.0  ", "220"),
        ("", ""),
        (None, ""),
    ],
)
def testNormalizeVoltageRemovesTrailingZeroes(value: object, expected: str) -> None:
    assert normalizeVoltage(value) == expected


def testNormalizeVoltageHandlesMultipleLevels() -> None:
    assert normalizeVoltage("380.0/110.0") == "380/110"


def testNormalizeVoltageKeepsNonNumericValues() -> None:
    assert normalizeVoltage("DC") == "DC"
    assert normalizeVoltage("DC/380.0") == "DC/380"


def testSplitVoltagesReturnsSingleValues() -> None:
    assert splitVoltages("380.0/110.0") == ["380", "110"]
    assert splitVoltages("380.0") == ["380"]
    assert splitVoltages("") == []


# --------------------------------------------------------------------------- #
# Koordinaten (Fall 5)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("52.459373", "52.459373"),
        ("52,459373", "52.459373"),
        (52.459373, "52.459373"),
        ("  52,459373 ", "52.459373"),
        ("-33,86", "-33.86"),
        (0, "0"),
    ],
)
def testNormalizeLatitudeAcceptsDecimalComma(value: object, expected: str) -> None:
    assert normalizeLatitude(value) == expected


def testNormalizeLatitudeRejectsOutOfRange() -> None:
    with pytest.raises(NormalizationError):
        normalizeLatitude("91.0")


def testNormalizeLongitudeRejectsOutOfRange() -> None:
    with pytest.raises(NormalizationError):
        normalizeLongitude("181.0")


def testNormalizeCoordinateRejectsText() -> None:
    with pytest.raises(NormalizationError):
        normalizeLongitude("nord")


def testNormalizeCoordinateRejectsEmpty() -> None:
    with pytest.raises(NormalizationError):
        normalizeLatitude("")


def testNormalizeCoordinateResolvesAmbiguousSeparators() -> None:
    """Punkt UND Komma: der letzte Separator gilt als Dezimaltrenner."""
    ambiguous: list[str] = []
    result = normalizeCoordinate("1.234,56", limits=(-2000.0, 2000.0), ambiguous=ambiguous)
    assert result == "1234.56"
    assert ambiguous == ["1.234,56"]


# --------------------------------------------------------------------------- #
# Datum (Fall 9, 10)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2025-05-09", "09.05.2025"),
        ("09/05/2025", "09.05.2025"),
        ("2025-05-09 00:00:00", "09.05.2025"),
        ("09.05.2025", "09.05.2025"),
        ("2025-05-09T00:00:00", "09.05.2025"),
        (dt.datetime(2025, 5, 9), "09.05.2025"),
        (dt.date(2025, 5, 9), "09.05.2025"),
        (45786, "09.05.2025"),  # Excel-Seriennummer
        ("", ""),
        (None, ""),
    ],
)
def testNormalizeDateProducesGermanFormat(value: object, expected: str) -> None:
    assert normalizeDate(value) == expected


@pytest.mark.parametrize("value", ["kaputt", "2025-13-45", "irgendwann", "31.02.2025"])
def testNormalizeDateRejectsUnparsableValues(value: str) -> None:
    with pytest.raises(NormalizationError):
        normalizeDate(value)


# --------------------------------------------------------------------------- #
# Boolean (Fall 19-21)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("value", [1, "1", True, "True", "true", "TRUE", 1.0])
def testParseBooleanRecognizesTrue(value: object) -> None:
    assert parseBoolean(value) is True


@pytest.mark.parametrize("value", [0, "0", False, "False", "false", "FALSE", "", None, float("nan")])
def testParseBooleanRecognizesFalse(value: object) -> None:
    assert parseBoolean(value) is False


@pytest.mark.parametrize("value", ["maybe", "yesplease", 2, "ja", "-1"])
def testParseBooleanReturnsNoneForUnknownValues(value: object) -> None:
    assert parseBoolean(value) is None


# --------------------------------------------------------------------------- #
# Text / ELEMENT-TYPE / Stationskennung
# --------------------------------------------------------------------------- #


def testNormalizeTextTrimsAndKeepsIntegers() -> None:
    assert normalizeText("  HRA_380 ") == "HRA_380"
    assert normalizeText(123.0) == "123"
    assert normalizeText(None) == ""
    assert normalizeText(float("nan")) == ""


def testNormalizeElementTypeIsCaseInsensitive() -> None:
    assert normalizeElementType("sub") == "SUB"
    assert normalizeElementType(" Line ") == "LINE"


@pytest.mark.parametrize(
    ("elementId", "name", "level"),
    [
        ("HRA_380", "HRA", "380"),
        ("Xb_380", "Xb", "380"),
        ("Station_A_110", "Station_A", "110"),
        ("NoUnderscore", "NoUnderscore", ""),
    ],
)
def testSplitStationIdUsesLastUnderscore(elementId: str, name: str, level: str) -> None:
    assert splitStationId(elementId) == (name, level)


@pytest.mark.parametrize("elementId", ["Xb_380", "Xfoo_220", "X_380"])
def testIsVirtualStationDetectsXNodes(elementId: str) -> None:
    assert isVirtualStation(elementId) is True


@pytest.mark.parametrize("elementId", ["Berlin_380", "HRA_380", "aX_380"])
def testIsVirtualStationIgnoresRealStations(elementId: str) -> None:
    assert isVirtualStation(elementId) is False
