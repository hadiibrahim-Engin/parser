"""Select supported rows and ignore Multipod summaries before validation."""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import replace

import numpy as np

from excelToCsv.normalize import normalizeElementType
from excelToCsv.multipod import findMultipodSummaryRows
from excelToCsv.reader import InputTable, columnValues
from excelToCsv.schema import COL_ELEMENT_TYPE, CONVERSION_ELEMENT_TYPES


def selectConversionRows(table: InputTable, logger: logging.Logger) -> InputTable:
    """Ignore out-of-scope rows while preserving physical Excel row numbers.

    Idempotent so file-based, in-memory and partial conversions share the same
    selection policy. Ignored rows never enter findings or dependency closure.
    """
    types = [normalizeElementType(value)
             for value in columnValues(table.frame, COL_ELEMENT_TYPE)]
    keep = np.array([kind in CONVERSION_ELEMENT_TYPES for kind in types], dtype=bool)
    if not keep.all():
        ignored = Counter(kind or "<empty>" for kind, selected in zip(types, keep)
                          if not selected)
        logger.info("Ignoring %d input row(s) outside the conversion types: %s.",
                    int((~keep).sum()),
                    ", ".join(f"{kind}: {count}" for kind, count in sorted(ignored.items())))
        table = replace(table, frame=table.frame.loc[keep].reset_index(drop=True),
                        rowNumbers=table.rowNumbers[keep])

    summaries = findMultipodSummaryRows(table)
    if not summaries:
        return table
    logger.info("Ignoring %d redundant Multipod summary row(s), Excel rows: %s.",
                len(summaries), ', '.join(str(row) for row in sorted(summaries)))
    keep = np.array([int(row) not in summaries for row in table.rowNumbers], dtype=bool)
    return replace(table, frame=table.frame.loc[keep].reset_index(drop=True),
                   rowNumbers=table.rowNumbers[keep])
