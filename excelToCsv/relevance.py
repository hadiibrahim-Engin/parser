"""Dynamische Erkennung und Auswertung der ``Interesting/Relevant for``-Spalten.

Die Spaltennamen variieren zwischen Lieferungen, deshalb werden sie anhand
eines Musters erkannt und der Betreiber-/Organisationsname aus dem Header
extrahiert. Ergebnis ist pro Zeile eine echte JSON-Liste als String.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from excelToCsv.issues import IssueCollector
from excelToCsv.normalize import collapseWhitespace, parseBoolean
from excelToCsv.reader import columnValues
from excelToCsv.schema import KNOWN_INPUT_COLUMNS

#: Header, die auf eine Relevanz-Spalte hindeuten.
_RELEVANCE_PATTERN: Final = re.compile(r"relevant\s*for|interesting", re.IGNORECASE)

#: Header-Präfixe, die trotz Treffer ausdrücklich ignoriert werden.
_EXCLUDED_PREFIXES: Final[tuple[str, ...]] = ("interconnector",)

#: Bekannte Fachspalten sind niemals Relevanz-Spalten.
_EXCLUDED_EXACT: Final[frozenset[str]] = frozenset(
    name.lower() for name in KNOWN_INPUT_COLUMNS
)

_LABEL_IN_PARENTHESES: Final = re.compile(r"\(([^)]*)\)")
_LABEL_NOISE: Final = re.compile(r"interesting|relevant|\bfor\b", re.IGNORECASE)

#: Ab dieser Spaltenanzahl lohnt die Bitmaske-Optimierung nicht mehr sicher.
_MAX_PACKED_COLUMNS: Final = 62

_EMPTY_LIST_JSON: Final = "[]"


def toJsonList(values: list[str]) -> str:
    """Serialisiert eine Werteliste als kompakte JSON-Liste (``["a","b"]``)."""
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class RelevanceColumn:
    """Zuordnung einer erkannten Inputspalte zu ihrem Organisationsnamen."""

    column: str
    label: str


def extractRelevanceLabel(header: str) -> str:
    """Extrahiert den Betreibernamen aus einem Relevanz-Header.

    ``"Interesting/Relevant for (50Hertz)"`` -> ``"50Hertz"``.
    Ohne Klammern werden die Schlüsselwörter entfernt und der Rest verwendet.
    """
    match = _LABEL_IN_PARENTHESES.search(header)
    if match and match.group(1).strip():
        return match.group(1).strip()
    cleaned = _LABEL_NOISE.sub(" ", header)
    return collapseWhitespace(cleaned).strip(" -:/_.")


def extractRelevanceColumns(
    columns: list[str],
    logger: logging.Logger,
) -> list[RelevanceColumn]:
    """Findet alle Relevanz-Spalten und ihre Labels in der Spaltenliste."""
    detected: list[RelevanceColumn] = []
    for column in columns:
        header = collapseWhitespace(str(column))
        lowered = header.lower()
        if lowered in _EXCLUDED_EXACT or lowered.startswith(_EXCLUDED_PREFIXES):
            continue
        if not _RELEVANCE_PATTERN.search(header):
            continue
        label = extractRelevanceLabel(header)
        if not label:
            logger.warning(
                "Cannot derive an organisation name from relevance column %r - column ignored.",
                header,
            )
            continue
        detected.append(RelevanceColumn(column=column, label=label))

    if detected:
        logger.info(
            "Detected %d relevance column(s): %s",
            len(detected),
            ", ".join(f"{item.column} -> {item.label}" for item in detected),
        )
    else:
        logger.warning("No 'Interesting/Relevant for' column detected - 'relevant für' stays [].")
    return detected


def buildRelevantFor(
    frame: pd.DataFrame,
    relevanceColumns: list[RelevanceColumn],
    rowNumbers: np.ndarray,
    elementIds: np.ndarray,
    elementTypes: np.ndarray,
    collector: IssueCollector,
) -> np.ndarray:
    """Baut die Spalte ``relevant für`` als JSON-Listen-Strings.

    Unbekannte Boolean-Werte (z. B. ``maybe``, ``2``) werden NICHT als ``True``
    interpretiert, sondern als ``WARNING`` gemeldet.
    """
    rowCount = len(frame)
    if rowCount == 0:
        return np.empty(0, dtype=object)
    if not relevanceColumns:
        return np.full(rowCount, _EMPTY_LIST_JSON, dtype=object)

    flags = np.zeros((rowCount, len(relevanceColumns)), dtype=bool)
    for columnIndex, relevance in enumerate(relevanceColumns):
        values = columnValues(frame, relevance.column)
        for position, value in enumerate(values):
            parsed = parseBoolean(value)
            if parsed is None:
                collector.warning(
                    "Unrecognized boolean value - not interpreted as TRUE.",
                    row=int(rowNumbers[position]),
                    elementId=elementIds[position],
                    elementType=elementTypes[position],
                    field=relevance.column,
                    value=value,
                    action="Treating the entry as not relevant and continuing.",
                )
                continue
            flags[position, columnIndex] = parsed

    labels = [item.label for item in relevanceColumns]
    if len(labels) > _MAX_PACKED_COLUMNS:  # pragma: no cover - defensiver Fallback
        return np.fromiter(
            (toJsonList(_uniqueLabels(labels, row)) for row in flags),
            dtype=object,
            count=rowCount,
        )

    # Jede Zeile wird auf eine Bitmaske reduziert; gleiche Muster teilen sich
    # dieselbe JSON-Zeichenkette. Das spart bei großen Dateien viele Serialisierungen.
    weights = (np.uint64(1) << np.arange(len(labels), dtype=np.uint64)).astype(np.int64)
    codes = flags.astype(np.int64) @ weights
    jsonByCode = {
        int(code): toJsonList(
            _uniqueLabels(labels, [(int(code) >> bit) & 1 for bit in range(len(labels))])
        )
        for code in np.unique(codes)
    }
    return np.fromiter((jsonByCode[int(code)] for code in codes), dtype=object, count=rowCount)


def _uniqueLabels(labels: list[str], flags: object) -> list[str]:
    """Sammelt die gesetzten Labels in Spaltenreihenfolge, ohne Dubletten."""
    selected: list[str] = []
    seen: set[str] = set()
    for label, flag in zip(labels, flags):  # type: ignore[arg-type]
        if flag and label not in seen:
            seen.add(label)
            selected.append(label)
    return selected
