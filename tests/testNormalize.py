"""Unit tests for the pure normalization functions."""

from __future__ import annotations

import datetime as dt
from collections import Counter

import pytest

from excelToCsv.errors import NormalizationError
from excelToCsv.normalize import (
    LATITUDE_RANGE,
    LONGITUDE_RANGE,
    buildMjapId,
    decimalPlaceCount,
    followsStationIdConvention,
    isRelevant,
    isVirtualStation,
    normalizeCoordinate,
    normalizeDate,
    normalizeElementType,
    normalizeLatitude,
    normalizeLongitude,
    normalizeText,
    normalizeVoltage,
    parseBoolean,
    repairByWidestFit,
    splitStationId,
    splitVoltages,
)
from excelToCsv.stations import dominantDecimalPlaces


# --------------------------------------------------------------------------- #
# Voltage (cases 6, 7)
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
# Coordinates (case 5)
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
    result = normalizeLatitude(value)
    assert result.text == expected
    assert result.repair == "", "a well-formed value needs no repair"


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
    """Dot AND comma: the last separator counts as the decimal separator."""
    result = normalizeCoordinate("1.234,56", limits=(-2000.0, 2000.0))
    assert result.text == "1234.56"
    assert "both '.' and ','" in result.repair


# --------------------------------------------------------------------------- #
# Missing decimal separator
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "decimals", "expected"),
    [
        ("52459373", 6, "52.459373"),
        (52459373, 6, "52.459373"),
        ("-52459373", 6, "-52.459373"),
        ("5245937", 5, "52.45937"),
        ("899999", 4, "89.9999"),
    ],
)
def testMissingSeparatorIsRepairedForLatitude(
    value: object, decimals: int, expected: str
) -> None:
    result = normalizeLatitude(value, decimals)
    assert result.text == expected
    assert "no decimal separator" in result.repair


def testMissingSeparatorUsesTheGivenPrecisionNotTheWidestFit() -> None:
    """13361402 is 13.361402 at 6 decimals - never the equally valid 133.61402."""
    assert normalizeLongitude("13361402", 6).text == "13.361402"
    assert normalizeLongitude("13361402", 5).text == "133.61402"


def testMissingSeparatorIsFatalWithoutPrecisionEvidence() -> None:
    """Without precision and without the explicit opt-in, nothing is guessed."""
    with pytest.raises(NormalizationError) as excinfo:
        normalizeLatitude("52459373")
    assert "decimal separator appears to be missing" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# Last resort: guessing the position
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("digits", "limits", "expected"),
    [
        ("185737", LATITUDE_RANGE, "18.5737"),
        ("52459373", LATITUDE_RANGE, "52.459373"),
        ("-52459373", LATITUDE_RANGE, "-52.459373"),
        ("13361402", LONGITUDE_RANGE, "133.61402"),
        ("9993682", LONGITUDE_RANGE, "99.93682"),
        ("999999999999999999", LATITUDE_RANGE, None),  # nothing fits
        ("52a459373", LATITUDE_RANGE, None),  # not pure digits
    ],
)
def testRepairByWidestFit(
    digits: str, limits: tuple[float, float], expected: str | None
) -> None:
    """The separator goes as far right as the range still allows."""
    assert repairByWidestFit(digits, limits) == expected


def testWidestFitNeedsTheExplicitOptIn() -> None:
    with pytest.raises(NormalizationError):
        normalizeCoordinate("185737", limits=LATITUDE_RANGE)

    guessed = normalizeCoordinate("185737", limits=LATITUDE_RANGE, allowWidestFit=True)
    assert guessed.text == "18.5737"
    assert "GUESSED" in guessed.repair
    assert "PLEASE VERIFY" in guessed.repair


def testPrecisionWinsOverTheGuess() -> None:
    """With a known precision the guess is never consulted."""
    derived = normalizeCoordinate(
        "9993682", limits=LONGITUDE_RANGE, decimalPlaces=6, allowWidestFit=True
    )
    assert derived.text == "9.993682"
    assert "GUESSED" not in derived.repair


def testValueInRangeIsNeverRepaired() -> None:
    """A whole number inside the valid range is a legitimate coordinate."""
    result = normalizeLatitude(52, 6)
    assert result.text == "52"
    assert result.repair == ""


def testOutOfRangeWithSeparatorStaysFatal() -> None:
    """A real out-of-range error must not be disguised as a missing separator."""
    with pytest.raises(NormalizationError) as excinfo:
        normalizeLatitude("152.5", 6)
    assert "out of range" in str(excinfo.value)


@pytest.mark.parametrize(
    ("value", "decimals"),
    [
        ("524", 6),  # fewer digits than decimals -> would fabricate a near-zero value
        ("52459373", 0),  # no usable precision
        ("999999999999", 2),  # still out of range after the repair
        ("52a459373", 6),  # not a pure digit sequence
    ],
)
def testUnrepairableValuesStayFatal(value: str, decimals: int) -> None:
    with pytest.raises(NormalizationError):
        normalizeLatitude(value, decimals)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("52.459373", 6), ("52.45", 2), ("52", 0), ("-9.1", 1)],
)
def testDecimalPlaceCount(text: str, expected: int) -> None:
    assert decimalPlaceCount(text) == expected


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({6: 10, 5: 2}, 6),
        ({0: 99, 4: 1}, 4),  # whole numbers are no evidence of precision
        ({5: 3, 6: 3}, 6),  # tie -> keep the higher precision
        ({}, None),
        ({0: 5}, None),
    ],
)
def testDominantDecimalPlaces(counts: dict[int, int], expected: int | None) -> None:
    assert dominantDecimalPlaces(Counter(counts)) == expected


# --------------------------------------------------------------------------- #
# Dates (cases 9, 10)
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
        (45786, "09.05.2025"),  # Excel serial number
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
# Booleans (cases 19-21)
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
# Text / ELEMENT-TYPE / station identifiers
# --------------------------------------------------------------------------- #


def testNormalizeTextTrimsAndKeepsIntegers() -> None:
    assert normalizeText("  HRA_380 ") == "HRA_380"
    assert normalizeText(123.0) == "123"
    assert normalizeText(None) == ""
    assert normalizeText(float("nan")) == ""


def testNormalizeElementTypeIsCaseInsensitive() -> None:
    assert normalizeElementType("sub") == "SUB"
    assert normalizeElementType(" Line ") == "LINE"


def testMjapIdCombinesOwnerAndElementId() -> None:
    assert buildMjapId(" Amprion ", " Berlin_380 ") == "Amprion_Berlin_380"
    assert buildMjapId("", "Berlin_380") == ""
    assert buildMjapId("Amprion", "") == ""


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


@pytest.mark.parametrize(
    ("elementId", "voltageLevel", "expected"),
    [
        ("Berlin_380", "380.0", True),
        ("Station_A_110", "380/110", True),
        ("Station_A_380/110", "380.0/110.0", True),
        ("Berlin", "380", False),
        ("Berlin_voltage", "380", False),
        ("Berlin_220", "380", False),
        ("_380", "380", False),
        ("Berlin_", "380", False),
    ],
)
def testStationIdConventionChecksTheVoltageSuffix(
    elementId: str, voltageLevel: object, expected: bool
) -> None:
    assert followsStationIdConvention(elementId, voltageLevel) is expected


@pytest.mark.parametrize("elementId", ["Xb_380", "Xfoo_220", "X_380"])
def testIsVirtualStationDetectsXNodes(elementId: str) -> None:
    assert isVirtualStation(elementId) is True


@pytest.mark.parametrize("elementId", ["Berlin_380", "HRA_380", "aX_380"])
def testIsVirtualStationIgnoresRealStations(elementId: str) -> None:
    assert isVirtualStation(elementId) is False


# --------------------------------------------------------------------------- #
# Several dates in one field
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("09.09.1900;02.05.2011", "09.09.1900;02.05.2011"),
        ("2025-05-09;09/05/2025", "09.05.2025;09.05.2025"),
        ("09.09.1900; 02.05.2011 ", "09.09.1900;02.05.2011"),
        ("2025-05-09;2026-01-31;2027-12-01", "09.05.2025;31.01.2026;01.12.2027"),
        ("09.05.2025;", "09.05.2025"),
        (";;", ""),
    ],
)
def testNormalizeDateHandlesSeveralDates(value: str, expected: str) -> None:
    """IBN/ABN may carry more than one date, separated by a semicolon."""
    assert normalizeDate(value) == expected


def testOneBrokenDateInAListIsFatal() -> None:
    with pytest.raises(NormalizationError):
        normalizeDate("2025-05-09;kaputt")


# --------------------------------------------------------------------------- #
# Relevance markers: I and R select the same organisation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value",
    ["I", "R", "i", "r", " I ", "\tr\n"],
)
def testIsRelevantAcceptsInterestingAndRelevant(value: object) -> None:
    assert isRelevant(value) is True


@pytest.mark.parametrize(
    "value",
    [0, "0", 0.0, "0.0", " 0 "],
)
def testIsRelevantRejectsExplicitZero(value: object) -> None:
    assert isRelevant(value) is False


@pytest.mark.parametrize("value", ["", "   ", None, float("nan")])
def testIsRelevantTreatsBlankAsNotRelevant(value: object) -> None:
    """An empty cell is no marker at all."""
    assert isRelevant(value) is False


@pytest.mark.parametrize("value", [1, "1", 2, "x", "l", "true", "false", True, False, "unknown"])
def testIsRelevantRejectsUnknownMarkers(value):
    with pytest.raises(NormalizationError, match="Unknown relevance marker"):
        isRelevant(value)
