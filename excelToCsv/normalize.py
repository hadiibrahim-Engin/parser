"""Pure normalization functions for individual cell values.

Every function here is side-effect free and does no I/O, which makes them
individually testable and allows them to be applied column-wise (vectorized).

Convention: a value that cannot be interpreted reliably raises a
:class:`~excelToCsv.errors.NormalizationError`. Nothing is ever guessed and no
broken value is silently passed through.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass
from typing import Final

from excelToCsv.errors import NormalizationError

# --------------------------------------------------------------------------- #
# Text / empty values
# --------------------------------------------------------------------------- #

#: Characters stripped as whitespace at the edges (including NBSP).
_WHITESPACE: Final = " \t\r\n\v\f   ﻿"

_INNER_WHITESPACE: Final = re.compile(r"[\s ]+")


def isBlank(value: object) -> bool:
    """Return ``True`` for ``None``, ``NaN``, ``NaT`` or pure whitespace."""
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    if value is not value:  # pragma: no cover - covers exotic NA sentinels
        return True
    if isinstance(value, str):
        return not value.strip(_WHITESPACE)
    return str(value).strip(_WHITESPACE) == ""


def normalizeText(value: object) -> str:
    """Convert a cell value into trimmed text; empty values become ``""``.

    Integral floats (Excel often delivers ``123.0``) are rendered as ``"123"``
    so that no artificial ``.0`` suffix ends up in identifiers.
    """
    if isBlank(value):
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, str):
        return value.strip(_WHITESPACE)
    if isinstance(value, (dt.datetime, dt.date)):
        return normalizeDate(value)
    return str(value).strip(_WHITESPACE)


def collapseWhitespace(value: str) -> str:
    """Trim and reduce inner runs of whitespace to a single space."""
    return _INNER_WHITESPACE.sub(" ", value).strip()


# --------------------------------------------------------------------------- #
# ELEMENT-TYPE
# --------------------------------------------------------------------------- #


def normalizeElementType(value: object) -> str:
    """Normalize ``ELEMENT-TYPE`` to uppercase (the check is case-insensitive)."""
    return normalizeText(value).upper()


# --------------------------------------------------------------------------- #
# Voltage
# --------------------------------------------------------------------------- #

_VOLTAGE_SEPARATOR: Final = "/"
_NUMERIC_TOKEN: Final = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")


def normalizeVoltageToken(token: str) -> str:
    """Normalize a single voltage value.

    Numeric values lose a redundant ``.0`` suffix (``380.0`` -> ``380``).
    Non-numeric business values such as ``DC`` are kept unchanged - they must not
    be destroyed by a numeric conversion.
    """
    token = token.strip(_WHITESPACE)
    if not token or not _NUMERIC_TOKEN.match(token):
        return token
    number = float(token.replace(",", "."))
    if number.is_integer():
        return str(int(number))
    return f"{number:f}".rstrip("0").rstrip(".")


def splitVoltages(value: object) -> list[str]:
    """Split ``VOLTAGE-LEVEL`` into individual normalized voltages.

    ``"380.0/110.0"`` -> ``["380", "110"]``; ``"DC"`` -> ``["DC"]``;
    empty -> ``[]``.
    """
    text = normalizeText(value)
    if not text:
        return []
    return [
        normalized
        for part in text.split(_VOLTAGE_SEPARATOR)
        if (normalized := normalizeVoltageToken(part))
    ]


def normalizeVoltage(value: object) -> str:
    """Normalized voltage as text (``"380/110"``), never as a number."""
    return _VOLTAGE_SEPARATOR.join(splitVoltages(value))


# --------------------------------------------------------------------------- #
# Coordinates
# --------------------------------------------------------------------------- #

LATITUDE_RANGE: Final = (-90.0, 90.0)
LONGITUDE_RANGE: Final = (-180.0, 180.0)

_COORDINATE_EXPECTATION: Final = (
    "A decimal number using '.' or ',' as decimal separator."
)

#: Longest digit sequence still plausible as a coordinate that lost its separator.
#: A longitude uses at most 3 integer digits, and 9 decimals already resolve well
#: below a millimetre - anything longer is corrupt data, not a missing separator.
MAX_GUESSABLE_DIGITS: Final = 12


@dataclass(frozen=True, slots=True)
class CoordinateValue:
    """A normalized coordinate together with a note about any repair applied.

    ``repair`` is empty when the value was already well-formed. Otherwise it
    describes, in one human-readable sentence, what was changed - the caller
    turns that into a ``WARNING`` carrying the full row context.
    """

    text: str
    repair: str = ""


def decimalPlaceCount(text: str) -> int:
    """Return how many digits follow the decimal point in a normalized value."""
    _, separator, decimals = text.partition(".")
    return len(decimals) if separator else 0


def repairMissingSeparator(
    text: str,
    decimalPlaces: int,
    limits: tuple[float, float],
) -> str | None:
    """Reinsert a decimal separator that was forgotten in the source data.

    ``"52459373"`` with ``decimalPlaces=6`` becomes ``"52.459373"``. The number of
    decimal places cannot be derived from the value itself - ``13361402`` is
    equally consistent with ``13.361402`` and ``133.61402`` - so the caller must
    supply the precision observed in the intact values of the same column.

    Returns:
        The repaired text, or ``None`` when no reliable repair is possible
        (non-digit characters, too few digits, or still out of range).
    """
    sign = "-" if text.startswith("-") else ""
    digits = text.lstrip("+-")
    if not digits.isdigit():
        return None
    if decimalPlaces <= 0 or len(digits) <= decimalPlaces:
        # Without at least one leading integer digit the result would be a
        # fabricated near-zero value rather than a repair.
        return None

    repaired = f"{sign}{digits[:-decimalPlaces]}.{digits[-decimalPlaces:]}"
    low, high = limits
    if not low <= float(repaired) <= high:
        return None
    return repaired


def repairByWidestFit(text: str, limits: tuple[float, float]) -> str | None:
    """Guess the separator position: as far right as the valid range still allows.

    Last-resort fallback for a column in which no single value carries a decimal
    separator, so there is no precision to derive. ``185737`` becomes ``18.5737``
    for a latitude.

    This is a **guess, not a reconstruction**. It is right whenever the original
    integer part used the maximum number of digits the range permits, and wrong
    otherwise: a longitude of ``9.993682`` written as ``9993682`` comes back as
    ``99.93682``, because the range allows three integer digits. Callers must
    surface the result as a warning telling the user to verify it.

    Because a single-digit integer part always fits, this rule would otherwise
    "repair" any digit sequence whatsoever. Sequences longer than
    :data:`MAX_GUESSABLE_DIGITS` are therefore rejected as corrupt data rather
    than turned into an implausibly precise coordinate.

    Returns:
        The guessed text, or ``None`` if the value is not plausibly a coordinate
        or no placement lands inside the range.
    """
    sign = "-" if text.startswith("-") else ""
    digits = text.lstrip("+-")
    if not digits.isdigit() or len(digits) > MAX_GUESSABLE_DIGITS:
        return None

    low, high = limits
    for integerDigits in range(len(digits) - 1, 0, -1):
        candidate = f"{sign}{digits[:integerDigits]}.{digits[integerDigits:]}"
        if low <= float(candidate) <= high:
            return candidate
    return None


def normalizeCoordinate(
    value: object,
    *,
    limits: tuple[float, float],
    decimalPlaces: int | None = None,
    allowWidestFit: bool = False,
) -> CoordinateValue:
    """Normalize a coordinate to use a dot as the decimal separator.

    Accepts ``52.459373``, ``"52,459373"`` and native Excel numbers. The value is
    range-checked against ``limits``.

    Two repairs may be applied, and each is reported through
    :attr:`CoordinateValue.repair` so the caller can log a warning:

    * both ``.`` and ``,`` present - the last separator is taken as the decimal
      separator,
    * decimal separator missing entirely and the value therefore out of range -
      the separator is reinserted using ``decimalPlaces``, or guessed via
      :func:`repairByWidestFit` when ``allowWidestFit`` is set.

    A value that is out of range but *does* carry a decimal separator is a
    genuine data error and is never repaired.

    Args:
        value: Raw value from the spreadsheet.
        limits: Permitted range as ``(min, max)``.
        decimalPlaces: Precision observed in the intact values of the same
            column, used to repair a missing separator. ``None`` disables that
            repair.
        allowWidestFit: Permit the last-resort guess when no precision is known.
            Only meaningful together with ``decimalPlaces=None``.

    Raises:
        NormalizationError: If the value is empty, not numeric, or out of range
            and not repairable.
    """
    if isBlank(value):
        raise NormalizationError(
            "Missing station coordinate.",
            "Every SUB station requires Latitude and Longitude.",
        )

    if isinstance(value, bool):
        raise NormalizationError("Coordinate is not a valid number.", _COORDINATE_EXPECTATION)

    repair = ""

    if isinstance(value, (int, float)):
        text = str(int(value)) if float(value).is_integer() else repr(float(value))
    else:
        text = str(value).strip(_WHITESPACE).replace(" ", "")
        if "," in text and "." in text:
            # Ambiguous: the separator occurring last is taken as the decimal one.
            decimalSeparator = "," if text.rfind(",") > text.rfind(".") else "."
            thousandsSeparator = "." if decimalSeparator == "," else ","
            cleaned = text.replace(thousandsSeparator, "").replace(decimalSeparator, ".")
            repair = (
                f"Coordinate contained both '.' and ',' - the last separator was read as "
                f"the decimal separator ({text} -> {cleaned})."
            )
            text = cleaned
        else:
            text = text.replace(",", ".")

    try:
        number = float(text)
    except ValueError:
        raise NormalizationError(
            "Coordinate is not a valid number.", _COORDINATE_EXPECTATION
        ) from None

    if math.isnan(number) or math.isinf(number):
        raise NormalizationError("Coordinate is not a finite number.", _COORDINATE_EXPECTATION)

    text = text.lstrip("+") or "0"
    low, high = limits
    if low <= number <= high:
        return CoordinateValue(text=text, repair=repair)

    if "." in text:
        raise NormalizationError(
            "Coordinate is out of range.",
            f"A value between {low:g} and {high:g}.",
        )

    # No decimal separator at all and out of range: the separator was most likely
    # forgotten when the sheet was filled in.
    if decimalPlaces is not None:
        repaired = repairMissingSeparator(text, decimalPlaces, limits)
        if repaired is not None:
            return CoordinateValue(
                text=repaired,
                repair=(
                    f"Coordinate had no decimal separator - it was reinserted using the "
                    f"{decimalPlaces}-decimal precision of this column "
                    f"({text} -> {repaired})."
                ),
            )
    elif allowWidestFit:
        repaired = repairByWidestFit(text, limits)
        if repaired is not None:
            return CoordinateValue(
                text=repaired,
                repair=(
                    f"Coordinate had no decimal separator and no other row of this column "
                    f"shows the intended precision - the separator was GUESSED by placing "
                    f"it as far right as the valid range allows ({text} -> {repaired}). "
                    f"PLEASE VERIFY: the guess is wrong whenever the true value has fewer "
                    f"integer digits than the range permits."
                ),
            )

    raise NormalizationError(
        "Coordinate is out of range and its decimal separator appears to be missing.",
        (
            f"A value between {low:g} and {high:g}. No decimal separator could be placed "
            f"anywhere inside that range."
        ),
    )


def normalizeLatitude(value: object, decimalPlaces: int | None = None) -> CoordinateValue:
    """Normalize a latitude (-90 .. 90)."""
    return normalizeCoordinate(value, limits=LATITUDE_RANGE, decimalPlaces=decimalPlaces)


def normalizeLongitude(value: object, decimalPlaces: int | None = None) -> CoordinateValue:
    """Normalize a longitude (-180 .. 180)."""
    return normalizeCoordinate(value, limits=LONGITUDE_RANGE, decimalPlaces=decimalPlaces)


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #

DATE_OUTPUT_FORMAT: Final = "%d.%m.%Y"

#: Excel serial numbers (1900 system) are relative to this origin.
_EXCEL_EPOCH: Final = dt.datetime(1899, 12, 30)
_EXCEL_SERIAL_RANGE: Final = (1.0, 2958465.0)  # 01.01.1900 .. 31.12.9999

#: Deterministic list of formats - nothing is ever guessed (no dayfirst heuristic).
_DATE_FORMATS: Final[tuple[str, ...]] = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y/%m/%d",
    "%d.%m.%Y",
    "%d.%m.%Y %H:%M:%S",
    "%d/%m/%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%Y",
    "%Y%m%d",
)

_DATE_EXPECTATION: Final = (
    "A parsable date, e.g. 2025-05-09, 09/05/2025, 09.05.2025 or an Excel date value."
)


#: Separator between several dates inside one IBN/ABN field.
DATE_SEPARATOR: Final = ";"


def normalizeDate(value: object) -> str:
    """Normalize one or several dates to ``DD.MM.YYYY``.

    A field may carry more than one date, separated by ``;`` - for example
    ``09.09.1900;02.05.2011``. Each part is normalized on its own and the parts
    are rejoined with the same separator, so the multi-date shape survives.

    An empty source value stays empty. A non-empty part that cannot be
    interpreted reliably is a fatal error.
    """
    if isBlank(value):
        return ""

    if isinstance(value, str) and DATE_SEPARATOR in value:
        parts = [part for part in value.split(DATE_SEPARATOR) if part.strip(_WHITESPACE)]
        if not parts:
            return ""
        return DATE_SEPARATOR.join(normalizeSingleDate(part) for part in parts)

    return normalizeSingleDate(value)


def normalizeSingleDate(value: object) -> str:
    """Normalize exactly one date value to ``DD.MM.YYYY``."""
    if isBlank(value):
        return ""

    if isinstance(value, dt.datetime):
        return value.strftime(DATE_OUTPUT_FORMAT)
    if isinstance(value, dt.date):
        return value.strftime(DATE_OUTPUT_FORMAT)

    if isinstance(value, bool):
        raise NormalizationError("Value is not a valid date.", _DATE_EXPECTATION)

    if isinstance(value, (int, float)):
        serial = float(value)
        low, high = _EXCEL_SERIAL_RANGE
        if not low <= serial <= high:
            raise NormalizationError(
                "Numeric value is not a plausible Excel date serial.", _DATE_EXPECTATION
            )
        return (_EXCEL_EPOCH + dt.timedelta(days=serial)).strftime(DATE_OUTPUT_FORMAT)

    text = str(value).strip(_WHITESPACE)
    for pattern in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, pattern).strftime(DATE_OUTPUT_FORMAT)
        except ValueError:
            continue

    try:
        return dt.datetime.fromisoformat(text).strftime(DATE_OUTPUT_FORMAT)
    except ValueError:
        raise NormalizationError("Value is not a valid date.", _DATE_EXPECTATION) from None


# --------------------------------------------------------------------------- #
# Booleans
# --------------------------------------------------------------------------- #

_TRUE_LITERALS: Final[frozenset[str]] = frozenset({"1", "true"})
_FALSE_LITERALS: Final[frozenset[str]] = frozenset({"0", "false"})

#: Interesting and relevant have the same meaning in the output.
RELEVANT_LITERALS: Final[frozenset[str]] = frozenset({"i", "r"})
NOT_RELEVANT_LITERALS: Final[frozenset[str]] = frozenset({"0", "0.0"})


def isRelevant(value: object) -> bool:
    """Decide whether a relevance marker counts as relevant.

    I (interesting) and R (relevant) both include the organisation. Zero and
    blank cells do not. Unknown markers are defects, not implicit selections.
    Matching is case-insensitive and trims surrounding whitespace.
    """
    if isBlank(value):
        return False
    marker = normalizeText(value).lower()
    if marker in RELEVANT_LITERALS:
        return True
    if marker in NOT_RELEVANT_LITERALS:
        return False
    raise NormalizationError(
        "Unknown relevance marker.",
        "I (interesting) or R (relevant); both select the organisation. "
        "0 or an empty cell means not relevant.",
    )


def parseBoolean(value: object) -> bool | None:
    """Interpret a boolean-like value.

    Returns:
        ``True`` / ``False`` for an unambiguous value, otherwise ``None``. In the
        ``None`` case nothing is guessed - the caller logs a ``WARNING`` and does
        *not* treat the entry as ``True``.
    """
    if isBlank(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        number = float(value)
        if number == 1.0:
            return True
        if number == 0.0:
            return False
        return None

    text = str(value).strip(_WHITESPACE).lower()
    if text in _TRUE_LITERALS:
        return True
    if text in _FALSE_LITERALS:
        return False
    return None


# --------------------------------------------------------------------------- #
# Station identifiers
# --------------------------------------------------------------------------- #

#: Prefix marking a virtual X node.
_VIRTUAL_PREFIX: Final = "X"

#: Separator between station name and voltage level inside an ``ELEMENT ID``.
STATION_ID_SEPARATOR: Final = "_"


def buildMjapId(owner: object, elementId: object) -> str:
    """Build ``<owner>_<ELEMENT ID>`` from normalized source values.

    An empty source produces an empty result so the transformation can collect
    a precise validation error instead of inventing part of an identifier.
    """
    normalizedOwner = normalizeText(owner)
    normalizedElementId = normalizeText(elementId)
    if not normalizedOwner or not normalizedElementId:
        return ""
    return f"{normalizedOwner}{STATION_ID_SEPARATOR}{normalizedElementId}"


def splitStationId(elementId: str) -> tuple[str, str]:
    """Split ``<stationName>_<voltageLevel>`` at the LAST ``_``.

    Without an underscore the whole id counts as the station name and the
    voltage level is empty.
    """
    name, separator, level = elementId.rpartition(STATION_ID_SEPARATOR)
    if not separator:
        return elementId, ""
    return name, level


def followsStationIdConvention(elementId: str, voltageLevel: object) -> bool:
    """Return whether an id follows ``<name>_<voltage-level>``.

    Merely containing an underscore is not sufficient: both parts must be
    populated and the suffix must agree with ``VOLTAGE-LEVEL`` after the same
    numeric normalization used for the output.  For aggregate station rows a
    suffix may name either one of the listed levels or their complete ``/``
    separated value.
    """
    name, level = splitStationId(elementId)
    if not name or not level:
        return False

    normalizedLevel = normalizeVoltage(level)
    expectedLevels = splitVoltages(voltageLevel)
    if not normalizedLevel or not expectedLevels:
        return False
    return normalizedLevel in expectedLevels or normalizedLevel == _VOLTAGE_SEPARATOR.join(
        expectedLevels
    )


def isVirtualStation(elementId: str) -> bool:
    """Return ``True`` when the name before the last ``_`` starts with ``X``."""
    name, _ = splitStationId(elementId)
    return name.startswith(_VIRTUAL_PREFIX)
