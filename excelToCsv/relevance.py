"""Dynamic detection and evaluation of the ``Interesting/Relevant for`` columns.

The column names vary between deliveries, so they are detected by pattern and
the operator/organisation name is extracted from the header. The result is a
semicolon-separated string per row.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Final

from excelToCsv.issues import IssueCollector
from excelToCsv.errors import NormalizationError
from excelToCsv.normalize import collapseWhitespace, isRelevant
from excelToCsv.reader import InputRow
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

#: Separator between several organisations in ``relevant für``.
RELEVANCE_SEPARATOR: Final = ";"


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


def relevantFor(row: InputRow, columns: list[RelevanceColumn], collector: IssueCollector) -> str:
    """The organisations a row is relevant for, as ``a;b;c`` (empty if none).

    I and R select the organisation equally; zero and blank cells do not.
    An unknown marker counts as not relevant and is reported with its source cell.
    """
    labels: list[str] = []
    for relevance in columns:
        value = row.cells.get(relevance.column)
        try:
            if isRelevant(value) and relevance.label not in labels:
                labels.append(relevance.label)
        except NormalizationError as error:
            collector.warning(error.problem, field=relevance.column, value=value,
                              expected=error.expected, action="Treated as not relevant.",
                              **row.context())
    return joinRelevance(labels)
