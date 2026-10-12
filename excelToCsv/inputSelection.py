"""Select supported rows and ignore Multipod summaries before validation."""
from __future__ import annotations

import logging
from collections import Counter

import numpy as np

from excelToCsv.issues import EMPTY_DISPLAY
from excelToCsv.multipod import findMultipodSummaryRows
from excelToCsv.reader import InputTable, elementTypeColumn
from excelToCsv.schema import CONVERSION_ELEMENT_TYPES


def selectConversionRows(table: InputTable, logger: logging.Logger) -> InputTable:
    """Ignore out-of-scope rows while preserving physical Excel row numbers.

    Idempotent so file-based, in-memory and partial conversions share the same
    selection policy. Ignored rows never enter findings or dependency closure.
    """
    types = elementTypeColumn(table.frame)
    keep = np.array([kind in CONVERSION_ELEMENT_TYPES for kind in types], dtype=bool)
    if not keep.all():
        ignored = Counter(kind or EMPTY_DISPLAY for kind, selected in zip(types, keep)
                          if not selected)
        logger.info("Ignoring %d input row(s) outside the conversion types: %s.",
                    int((~keep).sum()),
                    ", ".join(f"{kind}: {count}" for kind, count in sorted(ignored.items())))
        table = table.subset(keep)

    summaries = findMultipodSummaryRows(table)
    if not summaries:
        return table
    logger.info("Ignoring %d redundant Multipod summary row(s), Excel rows: %s.",
                len(summaries), ', '.join(str(row) for row in sorted(summaries)))
    return table.subset(~np.isin(table.rowNumbers, list(summaries)))
