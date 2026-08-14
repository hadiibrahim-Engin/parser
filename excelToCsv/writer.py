"""Schreiben der finalen CSV-Dateien.

Beide Dateien werden zunächst in temporäre Dateien im Zielverzeichnis
geschrieben und erst danach atomar an ihren endgültigen Namen verschoben.
So entsteht selbst bei einem I/O-Fehler kein halb geschriebener Output.
"""

from __future__ import annotations

import csv
import logging
import os
import tempfile
from pathlib import Path

import pandas as pd

from excelToCsv.errors import ConversionError
from excelToCsv.schema import NETWORK_ELEMENTS_FILENAME, STATIONS_FILENAME

#: Zeilenende laut Vertrag: ein einfaches LF, unabhängig vom Betriebssystem.
LINE_TERMINATOR = "\n"


def _writeSingleCsv(
    frame: pd.DataFrame,
    target: Path,
    encoding: str,
    quoting: int,
) -> None:
    """Schreibt einen DataFrame atomar nach ``target``."""
    handle, temporaryName = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    os.close(handle)
    temporary = Path(temporaryName)
    try:
        frame.to_csv(
            temporary,
            index=False,
            sep=",",
            encoding=encoding,
            quoting=quoting,
            lineterminator=LINE_TERMINATOR,
        )
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def writeCsvFiles(
    stations: pd.DataFrame,
    networkElements: pd.DataFrame,
    outputDir: Path,
    logger: logging.Logger,
    *,
    encoding: str = "utf-8",
    quoteAll: bool = False,
) -> tuple[Path, Path]:
    """Schreibt ``Stationen.csv`` und ``Netzelemente.csv``.

    Args:
        stations: Fertig validierter Stationen-Datensatz.
        networkElements: Fertig validierter Netzelemente-Datensatz.
        outputDir: Zielverzeichnis; wird bei Bedarf angelegt.
        logger: Logger für die Statusmeldungen.
        encoding: Zielkodierung (``utf-8-sig`` für Excel-freundliche BOM).
        quoteAll: ``True`` setzt jedes Feld in Anführungszeichen.

    Returns:
        Die Pfade beider geschriebener Dateien.

    Raises:
        ConversionError: Wenn das Verzeichnis oder eine Datei nicht schreibbar ist.
    """
    quoting = csv.QUOTE_ALL if quoteAll else csv.QUOTE_MINIMAL
    try:
        outputDir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Cannot create output directory %s: %s", outputDir, exc)
        raise ConversionError(f"Cannot create output directory: {outputDir}") from exc

    stationsPath = outputDir / STATIONS_FILENAME
    networkElementsPath = outputDir / NETWORK_ELEMENTS_FILENAME

    try:
        _writeSingleCsv(stations, stationsPath, encoding, quoting)
        logger.info("Created %s (%d record(s)).", stationsPath, len(stations))
        _writeSingleCsv(networkElements, networkElementsPath, encoding, quoting)
        logger.info("Created %s (%d record(s)).", networkElementsPath, len(networkElements))
    except OSError as exc:
        logger.error("Failed to write CSV output into %s: %s", outputDir, exc)
        raise ConversionError(f"Failed to write CSV output: {exc}") from exc

    return stationsPath, networkElementsPath
