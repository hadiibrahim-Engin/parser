"""One lifecycle policy shared by stations and network elements."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

from excelToCsv.context import ConversionContext, RowSet
from excelToCsv.normalize import normalizeDate
from excelToCsv.reader import applyNormalizer, columnValues
from excelToCsv.schema import COL_ENDLIFETIME, COL_STARTLIFETIME


def generatedLifecycleDates() -> tuple[str, str]:
    """MJAP's planning interval: today in Berlin through the end of 2100."""
    return datetime.now(ZoneInfo('Europe/Berlin')).strftime('%d.%m.%Y'), '31.12.2100'


def lifecycleColumns(rows: RowSet, context: ConversionContext) -> tuple[np.ndarray, np.ndarray]:
    """Generate MJAP dates, or normalize source dates for legacy conversion."""
    if context.lifecycleDates is not None:
        start, end = context.lifecycleDates
        return np.full(len(rows), start, dtype=object), np.full(len(rows), end, dtype=object)

    columns = []
    for column, target in ((COL_STARTLIFETIME, 'IBN'), (COL_ENDLIFETIME, 'ABN')):
        raw = columnValues(rows.frame, column)
        values, failures = applyNormalizer(raw, normalizeDate)
        for position, error in failures:
            context.collector.error(
                error.problem, field=column, value=raw[position],
                expected=f'{error.expected} Target column: {target} (DD.MM.YYYY).',
                **rows.context(position),
            )
        columns.append(values)
    return columns[0], columns[1]
