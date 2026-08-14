"""Reine Normalisierungsfunktionen für einzelne Zellwerte.

Alle Funktionen hier sind seiteneffektfrei und ohne I/O – dadurch sind sie
einzeln testbar und können spaltenweise (vektorisiert) angewendet werden.

Konvention: Ein Wert, der nicht zuverlässig interpretierbar ist, führt zu einer
:class:`~excelToCsv.errors.NormalizationError`. Es wird niemals geraten und
niemals ein kaputter Wert stillschweigend übernommen.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from typing import Final

from excelToCsv.errors import NormalizationError

# --------------------------------------------------------------------------- #
# Text / Leerwerte
# --------------------------------------------------------------------------- #

#: Zeichen, die als Whitespace am Rand entfernt werden (inkl. NBSP).
_WHITESPACE: Final = " \t\r\n\v\f   ﻿"

_INNER_WHITESPACE: Final = re.compile(r"[\s ]+")


def isBlank(value: object) -> bool:
    """``True`` für ``None``, ``NaN``, ``NaT`` oder reinen Whitespace."""
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    if value is not value:  # pragma: no cover - deckt exotische NA-Sentinels ab
        return True
    if isinstance(value, str):
        return not value.strip(_WHITESPACE)
    return str(value).strip(_WHITESPACE) == ""


def normalizeText(value: object) -> str:
    """Wandelt einen Zellwert in getrimmten Text; Leerwerte werden ``""``.

    Ganzzahlige Floats (Excel liefert häufig ``123.0``) werden als ``"123"``
    dargestellt, damit keine künstlichen ``.0``-Endungen in IDs landen.
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
    """Trimmt und reduziert innere Whitespace-Folgen auf ein Leerzeichen."""
    return _INNER_WHITESPACE.sub(" ", value).strip()


# --------------------------------------------------------------------------- #
# ELEMENT-TYPE
# --------------------------------------------------------------------------- #


def normalizeElementType(value: object) -> str:
    """Normalisiert ``ELEMENT-TYPE`` auf Uppercase (Prüfung case-insensitive)."""
    return normalizeText(value).upper()


# --------------------------------------------------------------------------- #
# Spannung
# --------------------------------------------------------------------------- #

_VOLTAGE_SEPARATOR: Final = "/"
_NUMERIC_TOKEN: Final = re.compile(r"^[+-]?\d+(?:[.,]\d+)?$")


def normalizeVoltageToken(token: str) -> str:
    """Normalisiert einen einzelnen Spannungswert.

    Numerische Werte verlieren überflüssige ``.0``-Endungen (``380.0`` ->
    ``380``). Nichtnumerische fachliche Werte (z. B. ``DC``) bleiben unverändert
    – sie dürfen nicht durch eine numerische Konvertierung zerstört werden.
    """
    token = token.strip(_WHITESPACE)
    if not token or not _NUMERIC_TOKEN.match(token):
        return token
    number = float(token.replace(",", "."))
    if number.is_integer():
        return str(int(number))
    return f"{number:f}".rstrip("0").rstrip(".")


def splitVoltages(value: object) -> list[str]:
    """Zerlegt ``VOLTAGE-LEVEL`` in einzelne normalisierte Spannungen.

    ``"380.0/110.0"`` -> ``["380", "110"]``; ``"DC"`` -> ``["DC"]``;
    leer -> ``[]``.
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
    """Normalisierte Spannung als Text (``"380/110"``), niemals als Zahl."""
    return _VOLTAGE_SEPARATOR.join(splitVoltages(value))


# --------------------------------------------------------------------------- #
# Koordinaten
# --------------------------------------------------------------------------- #

LATITUDE_RANGE: Final = (-90.0, 90.0)
LONGITUDE_RANGE: Final = (-180.0, 180.0)


def normalizeCoordinate(
    value: object,
    *,
    limits: tuple[float, float],
    ambiguous: list[str] | None = None,
) -> str:
    """Normalisiert eine Koordinate auf Punkt-Dezimaltrennzeichen.

    Akzeptiert ``52.459373``, ``"52,459373"`` sowie echte Excel-Zahlen. Der
    Wertebereich wird gegen ``limits`` geprüft.

    Args:
        value: Rohwert aus dem Excel.
        limits: Zulässiger Bereich (min, max).
        ambiguous: Optionale Liste, in die ein Hinweis geschrieben wird, wenn
            Punkt UND Komma vorkamen und heuristisch aufgelöst wurde.

    Raises:
        NormalizationError: Wenn der Wert leer, nicht numerisch oder außerhalb
            des zulässigen Bereichs ist.
    """
    if isBlank(value):
        raise NormalizationError(
            "Missing station coordinate.",
            "Every SUB station requires Latitude and Longitude.",
        )

    if isinstance(value, bool):
        raise NormalizationError(
            "Coordinate is not a valid number.",
            "A decimal number using '.' or ',' as decimal separator.",
        )

    if isinstance(value, (int, float)):
        text = str(int(value)) if float(value).is_integer() else repr(float(value))
    else:
        text = str(value).strip(_WHITESPACE).replace(" ", "")
        if "," in text and "." in text:
            # Mehrdeutig: das zuletzt auftretende Zeichen gilt als Dezimaltrenner.
            decimalSeparator = "," if text.rfind(",") > text.rfind(".") else "."
            thousandsSeparator = "." if decimalSeparator == "," else ","
            text = text.replace(thousandsSeparator, "").replace(decimalSeparator, ".")
            if ambiguous is not None:
                ambiguous.append(str(value))
        else:
            text = text.replace(",", ".")

    try:
        number = float(text)
    except ValueError:
        raise NormalizationError(
            "Coordinate is not a valid number.",
            "A decimal number using '.' or ',' as decimal separator.",
        ) from None

    if math.isnan(number) or math.isinf(number):
        raise NormalizationError(
            "Coordinate is not a finite number.",
            "A decimal number using '.' or ',' as decimal separator.",
        )

    low, high = limits
    if not low <= number <= high:
        raise NormalizationError(
            "Coordinate is out of range.",
            f"A value between {low:g} and {high:g}.",
        )

    return text.lstrip("+") or "0"


def normalizeLatitude(value: object, ambiguous: list[str] | None = None) -> str:
    """Normalisiert eine Breitengrad-Angabe (-90 .. 90)."""
    return normalizeCoordinate(value, limits=LATITUDE_RANGE, ambiguous=ambiguous)


def normalizeLongitude(value: object, ambiguous: list[str] | None = None) -> str:
    """Normalisiert eine Längengrad-Angabe (-180 .. 180)."""
    return normalizeCoordinate(value, limits=LONGITUDE_RANGE, ambiguous=ambiguous)


# --------------------------------------------------------------------------- #
# Datum
# --------------------------------------------------------------------------- #

DATE_OUTPUT_FORMAT: Final = "%d.%m.%Y"

#: Excel-Seriennummern beziehen sich (im 1900-System) auf diesen Ursprung.
_EXCEL_EPOCH: Final = dt.datetime(1899, 12, 30)
_EXCEL_SERIAL_RANGE: Final = (1.0, 2958465.0)  # 01.01.1900 .. 31.12.9999

#: Deterministische Formatliste – es wird nie geraten (kein dayfirst-Heuristik).
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


def normalizeDate(value: object) -> str:
    """Normalisiert ein Datum auf ``TT.MM.JJJJ``.

    Ein leerer Quellwert bleibt leer. Ein nicht leerer Wert, der nicht
    zuverlässig als Datum interpretiert werden kann, ist ein fataler Fehler.
    """
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
# Boolean
# --------------------------------------------------------------------------- #

_TRUE_LITERALS: Final[frozenset[str]] = frozenset({"1", "true"})
_FALSE_LITERALS: Final[frozenset[str]] = frozenset({"0", "false"})


def parseBoolean(value: object) -> bool | None:
    """Interpretiert einen Boolean-artigen Wert.

    Returns:
        ``True`` / ``False`` bei eindeutigem Wert, sonst ``None``. Bei ``None``
        wird bewusst nicht geraten – der Aufrufer loggt eine ``WARNING`` und
        behandelt den Eintrag NICHT als ``True``.
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
# Stationskennung
# --------------------------------------------------------------------------- #

#: Präfix, das einen virtuellen X-Knoten kennzeichnet.
_VIRTUAL_PREFIX: Final = "X"


def splitStationId(elementId: str) -> tuple[str, str]:
    """Zerlegt ``<Stationsname>_<Spannungsebene>`` am LETZTEN ``_``.

    Fehlt der Unterstrich, gilt die komplette ID als Stationsname und die
    Spannungsebene ist leer.
    """
    name, separator, level = elementId.rpartition("_")
    if not separator:
        return elementId, ""
    return name, level


def isVirtualStation(elementId: str) -> bool:
    """``True``, wenn der Stationsname vor dem letzten ``_`` mit ``X`` beginnt."""
    name, _ = splitStationId(elementId)
    return name.startswith(_VIRTUAL_PREFIX)
