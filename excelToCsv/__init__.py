"""Converter: Excel-Netzinventar -> ``Stationen.csv`` + ``Netzelemente.csv``."""

from __future__ import annotations

from excelToCsv.errors import ConversionError, NormalizationError
from excelToCsv.pipeline import ConversionResult, convertTable, runConversion
from excelToCsv.schema import NETWORK_ELEMENT_COLUMNS, STATION_COLUMNS

__all__ = [
    "ConversionError",
    "ConversionResult",
    "NormalizationError",
    "NETWORK_ELEMENT_COLUMNS",
    "STATION_COLUMNS",
    "convertTable",
    "runConversion",
]

__version__ = "1.0.0"
