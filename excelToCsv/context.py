"""What every conversion step needs: findings, logging, relevance columns, dates."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from excelToCsv.issues import IssueCollector
from excelToCsv.reader import InputRow
from excelToCsv.relevance import RelevanceColumn, relevantFor


@dataclass(slots=True)
class ConversionContext:
    """Shared state of one conversion run."""

    logger: logging.Logger
    collector: IssueCollector
    relevanceColumns: list[RelevanceColumn]
    #: IBN / ABN written for every station and network element.
    planningDates: tuple[str, str]

    def relevantFor(self, row: InputRow) -> str:
        return relevantFor(row, self.relevanceColumns, self.collector)
