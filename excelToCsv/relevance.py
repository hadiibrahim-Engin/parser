"""Dynamic detection and evaluation of the ``Interesting/Relevant for`` columns.

The column names vary between deliveries, so they are detected by pattern and
the operator/organisation name is extracted from the header. The result is a
semicolon-separated string per row.
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
from excelToCsv.normalize import NOT_RELEVANT_LITERALS, collapseWhitespace, isRelevant
from excelToCsv.reader import columnValues
from excelToCsv.schema import KNOWN_INPUT_COLUMNS

#: Headers that indicate a relevance column.
_RELEVANCE_PATTERN: Final = re.compile(r"relevant\s*for|interesting", re.IGNORECASE)

#: Header prefixes that are explicitly ignored even when they match.
_EXCLUDED_PREFIXES: Final[tuple[str, ...]] = ("interconnector",)

#: Known business columns are never relevance columns.
_EXCLUDED_EXACT: Final[frozenset[str]] = frozenset(
    name.lower() for name in KNOWN_INPUT_COLUMNS
)

_LABEL_IN_PARENTHESES: Final = re.compile(r"\(([^)]*)\)")
_LABEL_NOISE: Final = re.compile(r"interesting|relevant|\bfor\b", re.IGNORECASE)

#: Beyond this column count the bitmask optimization is no longer safe.
_MAX_PACKED_COLUMNS: Final = 62

#: Separator between several organisations in ``relevant für``.
RELEVANCE_SEPARATOR: Final = ";"

_EMPTY_RELEVANCE: Final = ""

#: Value representations that carry no information for the diagnostic.
_BLANK_REPRESENTATIONS: Final[frozenset[str]] = frozenset({"''", "None", "nan", "' '"})


def toJsonList(values: list[str]) -> str:
    """Serialize a list of values as a compact JSON list (``["a","b"]``).

    Still used for the station ``Spannung`` column, which stays a JSON list.
    """
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def joinRelevance(values: list[str]) -> str:
    """Join the relevant organisations into one semicolon-separated field.

    One organisation stays a plain name, several are written as ``a;b;c``, and
    none produces an empty field.
    """
    return RELEVANCE_SEPARATOR.join(values)


@dataclass(frozen=True, slots=True)
class RelevanceColumn:
    """Mapping of a detected input column to its organisation name."""

    column: str
    label: str


def extractRelevanceLabel(header: str) -> str:
    """Extract the operator name from a relevance header.

    ``"Interesting/Relevant for (50Hertz)"`` -> ``"50Hertz"``.
    Without parentheses the keywords are stripped and the remainder is used.
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
    """Find all relevance columns and their labels in the column list."""
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
        candidates = [
            column
            for column in columns
            if collapseWhitespace(str(column)).lower() not in _EXCLUDED_EXACT
        ]
        logger.warning(
            "No 'Interesting/Relevant for' column detected - 'relevant für' stays empty. "
            "A header must contain 'relevant for' or 'interesting'. Columns present that "
            "matched nothing: %s",
            ", ".join(repr(str(column)) for column in candidates) or "(none)",
        )
    return detected


def buildRelevantFor(
    frame: pd.DataFrame,
    relevanceColumns: list[RelevanceColumn],
    rowNumbers: np.ndarray,
    elementIds: np.ndarray,
    elementTypes: np.ndarray,
    collector: IssueCollector,
) -> np.ndarray:
    """Build the ``relevant für`` column as semicolon-separated organisations.

    Several organisations are written as ``50Hertz;TennetD``, a single one as a
    plain name, and none as an empty field.

    The relevance columns are free-text tick boxes: anything except an explicit
    zero counts as relevant, see :func:`~excelToCsv.normalize.isRelevant`.
    """
    rowCount = len(frame)
    if rowCount == 0:
        return np.empty(0, dtype=object)
    if not relevanceColumns:
        return np.full(rowCount, _EMPTY_RELEVANCE, dtype=object)

    flags = np.zeros((rowCount, len(relevanceColumns)), dtype=bool)
    for columnIndex, relevance in enumerate(relevanceColumns):
        values = columnValues(frame, relevance.column)
        seen: set[str] = set()
        for position, value in enumerate(values):
            seen.add(repr(value))
            flags[position, columnIndex] = isRelevant(value)

        meaningful = {value for value in seen if value not in _BLANK_REPRESENTATIONS}
        if not flags[:, columnIndex].any() and meaningful:
            # Every marker in this column reads as "not relevant". Legitimate, but
            # worth recording in the debug log when a column looks unexpectedly empty.
            collector.logger.debug(
                "Relevance column %r marks no row as relevant. Not relevant: %s. "
                "Values found in this column: %s",
                relevance.column,
                ", ".join(sorted(NOT_RELEVANT_LITERALS)),
                ", ".join(sorted(meaningful)[:12]),
            )

    labels = [item.label for item in relevanceColumns]
    if len(labels) > _MAX_PACKED_COLUMNS:  # pragma: no cover - defensive fallback
        return np.fromiter(
            (joinRelevance(_uniqueLabels(labels, row)) for row in flags),
            dtype=object,
            count=rowCount,
        )

    # Each row is reduced to a bitmask so identical patterns share one joined
    # string. On large files this saves a lot of string building.
    weights = (np.uint64(1) << np.arange(len(labels), dtype=np.uint64)).astype(np.int64)
    codes = flags.astype(np.int64) @ weights
    textByCode = {
        int(code): joinRelevance(
            _uniqueLabels(labels, [(int(code) >> bit) & 1 for bit in range(len(labels))])
        )
        for code in np.unique(codes)
    }
    return np.fromiter((textByCode[int(code)] for code in codes), dtype=object, count=rowCount)


def _uniqueLabels(labels: list[str], flags: object) -> list[str]:
    """Collect the set labels in column order, without duplicates."""
    selected: list[str] = []
    seen: set[str] = set()
    for label, flag in zip(labels, flags):  # type: ignore[arg-type]
        if flag and label not in seen:
            seen.add(label)
            selected.append(label)
    return selected
