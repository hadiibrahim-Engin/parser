"""Einlesen der Excel-Datei und Aufbereitung des Input-Schemas.

Verantwortlich für: Datei-I/O, Spaltennormalisierung, Schemaprüfung und das
Verwerfen komplett leerer Zeilen. Die fachliche Transformation findet
bewusst NICHT hier statt.
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from excelToCsv.errors import ConversionError, NormalizationError
from excelToCsv.normalize import collapseWhitespace, isBlank, normalizeText
from excelToCsv.schema import KNOWN_INPUT_COLUMNS, REQUIRED_INPUT_COLUMNS

#: Excel-Zeile 1 ist der Header, die erste Datenzeile ist demnach Zeile 2.
HEADER_ROW_OFFSET = 2

#: Standard-Engine. ``openpyxl`` ist immer verfügbar; ``calamine`` ist ein
#: optionaler Beschleuniger (Faktor ~5 beim Lesen) und wird nur genutzt,
#: wenn das Paket installiert ist.
DEFAULT_ENGINE = "auto"
FALLBACK_ENGINE = "openpyxl"
FAST_ENGINE = "calamine"


def resolveEngine(engine: str, logger: logging.Logger) -> str:
    """Wählt die Lese-Engine; ``auto`` bevorzugt ``calamine``, sonst ``openpyxl``."""
    if engine != DEFAULT_ENGINE:
        return engine
    if importlib.util.find_spec("python_calamine") is not None:
        logger.debug("Using the optional '%s' engine for faster reading.", FAST_ENGINE)
        return FAST_ENGINE
    return FALLBACK_ENGINE


@dataclass(slots=True)
class InputTable:
    """Eingelesene und aufbereitete Inputtabelle inklusive Excel-Zeilennummern."""

    frame: pd.DataFrame
    rowNumbers: np.ndarray
    sheetName: str

    def __len__(self) -> int:
        return len(self.frame)


def loadExcel(
    path: Path,
    sheet: str | int | None,
    logger: logging.Logger,
    engine: str = DEFAULT_ENGINE,
) -> tuple[pd.DataFrame, str]:
    """Liest ein Worksheet als reine Objekt-Tabelle ein.

    ``dtype=object`` verhindert, dass pandas Werte (IDs, Spannungen, Codes)
    eigenmächtig in Zahlen konvertiert. Ohne explizite Auswahl wird das erste
    Worksheet verwendet und dessen Name geloggt.

    Raises:
        ConversionError: Datei fehlt, ist unlesbar oder das Sheet existiert nicht.
    """
    if not path.is_file():
        logger.error("Input file not found: %s", path)
        raise ConversionError(f"Input file not found: {path}")

    selectedEngine = resolveEngine(engine, logger)
    logger.info("Reading input file: %s", path)
    try:
        with pd.ExcelFile(path, engine=selectedEngine) as workbook:
            sheetNames = list(workbook.sheet_names)
            if not sheetNames:
                logger.error("Workbook contains no worksheet: %s", path)
                raise ConversionError(f"Workbook contains no worksheet: {path}")

            if sheet is None:
                selected = sheetNames[0]
                if len(sheetNames) > 1:
                    logger.info(
                        "Workbook contains %d worksheets %s - using the first one.",
                        len(sheetNames),
                        sheetNames,
                    )
            elif isinstance(sheet, int):
                if not 0 <= sheet < len(sheetNames):
                    logger.error(
                        "Sheet index %d is out of range (workbook has %d worksheets).",
                        sheet,
                        len(sheetNames),
                    )
                    raise ConversionError(f"Sheet index out of range: {sheet}")
                selected = sheetNames[sheet]
            else:
                if sheet not in sheetNames:
                    logger.error("Sheet '%s' not found. Available: %s", sheet, sheetNames)
                    raise ConversionError(f"Sheet not found: {sheet}")
                selected = sheet

            logger.info("Using worksheet: %s", selected)
            frame = workbook.parse(sheet_name=selected, dtype=object)
    except ConversionError:
        raise
    except Exception as exc:  # openpyxl/pandas werfen sehr heterogene Fehler
        if selectedEngine != FALLBACK_ENGINE and engine == DEFAULT_ENGINE:
            logger.warning(
                "Reading with the '%s' engine failed (%s) - retrying with '%s'.",
                selectedEngine,
                exc,
                FALLBACK_ENGINE,
            )
            return loadExcel(path, sheet, logger, engine=FALLBACK_ENGINE)
        logger.error("Failed to read Excel file %s: %s", path, exc)
        raise ConversionError(f"Failed to read Excel file: {path}") from exc

    logger.info(
        "Read %d data row(s) and %d column(s) using the '%s' engine.",
        len(frame),
        len(frame.columns),
        selectedEngine,
    )
    return frame, selected


def normalizeColumns(frame: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Trimmt Spaltenüberschriften und führt sie auf die kanonische Schreibweise.

    Die Zuordnung erfolgt case-insensitiv und whitespace-tolerant. Unbekannte
    Spalten behalten ihren (getrimmten) Namen – sie werden für die dynamische
    Relevanz-Erkennung noch gebraucht.

    Raises:
        ConversionError: Wenn nach der Normalisierung doppelte Spalten entstehen.
    """
    canonicalByKey = {collapseWhitespace(name).lower(): name for name in KNOWN_INPUT_COLUMNS}

    renamed: list[str] = []
    for original in frame.columns:
        cleaned = collapseWhitespace(str(original))
        canonical = canonicalByKey.get(cleaned.lower(), cleaned)
        if canonical != str(original):
            logger.debug("Column %r normalized to %r.", str(original), canonical)
        renamed.append(canonical)

    duplicates = sorted({name for name in renamed if renamed.count(name) > 1})
    if duplicates:
        logger.error("Duplicate input columns after normalization: %s", ", ".join(duplicates))
        raise ConversionError(f"Duplicate input columns: {', '.join(duplicates)}")

    normalized = frame.copy()
    normalized.columns = pd.Index(renamed)
    return normalized


def validateRequiredInputColumns(frame: pd.DataFrame, logger: logging.Logger) -> None:
    """Stellt sicher, dass alle zwingend benötigten Inputspalten vorhanden sind.

    Raises:
        ConversionError: Sobald mindestens eine Pflichtspalte fehlt.
    """
    present = set(frame.columns)
    missing = [name for name in REQUIRED_INPUT_COLUMNS if name not in present]
    if missing:
        for name in missing:
            logger.error("Missing required input column: %s", name)
        raise ConversionError(f"Missing required input column(s): {', '.join(missing)}")
    logger.debug("All %d required input columns are present.", len(REQUIRED_INPUT_COLUMNS))


def dropEmptyRows(
    frame: pd.DataFrame,
    rowNumbers: np.ndarray,
    logger: logging.Logger,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Entfernt Zeilen, die in JEDER Spalte leer sind (typische Excel-Leerzeilen)."""
    if frame.empty:
        return frame, rowNumbers

    blank = np.ones(len(frame), dtype=bool)
    for column in frame.columns:
        values = frame[column].to_numpy(dtype=object)
        blank &= np.fromiter((isBlank(value) for value in values), dtype=bool, count=len(values))

    dropped = int(blank.sum())
    if not dropped:
        return frame, rowNumbers

    logger.info("Skipping %d completely empty input row(s).", dropped)
    keep = ~blank
    return frame.loc[keep].reset_index(drop=True), rowNumbers[keep]


def buildInputTable(
    path: Path,
    sheet: str | int | None,
    logger: logging.Logger,
    engine: str = DEFAULT_ENGINE,
) -> InputTable:
    """Kompletter Lesepfad: Excel -> validiertes, aufbereitetes ``InputTable``."""
    frame, sheetName = loadExcel(path, sheet, logger, engine=engine)
    frame = normalizeColumns(frame, logger)
    validateRequiredInputColumns(frame, logger)

    frame = frame.reset_index(drop=True)
    rowNumbers = np.arange(len(frame), dtype=np.int64) + HEADER_ROW_OFFSET
    frame, rowNumbers = dropEmptyRows(frame, rowNumbers, logger)
    return InputTable(frame=frame, rowNumbers=rowNumbers, sheetName=sheetName)


def columnValues(frame: pd.DataFrame, column: str) -> np.ndarray:
    """Liefert eine Spalte als Objekt-Array; fehlende Spalten werden zu ``None``."""
    if column in frame.columns:
        return frame[column].to_numpy(dtype=object)
    return np.full(len(frame), None, dtype=object)


def textColumn(frame: pd.DataFrame, column: str) -> np.ndarray:
    """Liefert eine Spalte als getrimmte Textwerte (Leerwerte werden ``""``)."""
    values = columnValues(frame, column)
    return np.fromiter(
        (normalizeText(value) for value in values), dtype=object, count=len(values)
    )


def applyNormalizer(
    values: np.ndarray,
    normalizer: Callable[[Any], str],
) -> tuple[np.ndarray, list[tuple[int, NormalizationError]]]:
    """Wendet einen Normalisierer spaltenweise an und sammelt Einzelfehler ein.

    Statt beim ersten Problem abzubrechen, wird jeder fehlerhafte Wert mit
    seiner Position gemeldet – so sieht der Anwender in einem Lauf alle Fehler.

    Returns:
        Tuple aus normalisierten Werten und ``(position, error)``-Paaren.
    """
    result = np.empty(len(values), dtype=object)
    failures: list[tuple[int, NormalizationError]] = []
    for position, value in enumerate(values):
        try:
            result[position] = normalizer(value)
        except NormalizationError as error:
            result[position] = ""
            failures.append((position, error))
    return result, failures
