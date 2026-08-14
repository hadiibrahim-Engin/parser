"""Colored, structured console logging.

Every status, warning and error message goes through ``logging`` - the converter
never uses ``print()``.

The formatter does three things beyond plain logging:

* it shows **where** a message came from (source file and line),
* it **indents** the detail lines of a multi-line block so they read as one unit,
* it **separates** multi-line blocks with a blank line so consecutive findings do
  not run into each other.

Colors come from ``colorlog`` when it is installed; otherwise a small built-in
ANSI table is used, so the converter never depends on it being present.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Final

LOGGER_NAME: Final = "excelToCsv"

#: Breite der Quellenangabe (``reader.py:120``) in der Log-Zeile.
LOCATION_WIDTH: Final = 22

#: ``%(levelname)-8s`` plus Trennzeichen – Folgezeilen richten sich daran aus.
CONTINUATION_INDENT: Final = " " * 9

_LOG_FORMAT: Final = f"%(levelname)-8s %(location)-{LOCATION_WIDTH}s %(message)s"

#: Farbnamen je Level (colorlog-Schreibweise).
_COLOR_NAMES: Final[dict[int, str]] = {
    logging.DEBUG: "thin_white",
    logging.INFO: "green",
    logging.WARNING: "yellow",
    logging.ERROR: "red",
    logging.CRITICAL: "bold_white,bg_red",
}

#: ANSI-Fallback je Level, falls ``colorlog`` fehlt.
_ANSI_COLORS: Final[dict[int, str]] = {
    logging.DEBUG: "\033[2;37m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[1;97;41m",
}
_ANSI_RESET: Final = "\033[0m"

#: Signatur einer Einfärbefunktion: (Level, Text) -> eingefärbter Text.
Colorizer = Callable[[int, str], str]


def plainColorizer(level: int, text: str) -> str:
    """Gibt den Text unverändert zurück (Farbe abgeschaltet)."""
    return text


def ansiColorizer(level: int, text: str) -> str:
    """Färbt den Text mit einer minimalen, eingebauten ANSI-Palette ein."""
    color = _ANSI_COLORS.get(level)
    return f"{color}{text}{_ANSI_RESET}" if color else text


def buildColorizer(useColor: bool) -> Colorizer:
    """Wählt die Einfärbung: ``colorlog``-Palette, ANSI-Fallback oder keine."""
    if not useColor:
        return plainColorizer
    try:
        from colorlog.escape_codes import parse_colors
    except ImportError:
        return ansiColorizer

    codes = {level: parse_colors(name) for level, name in _COLOR_NAMES.items()}
    reset = parse_colors("reset")

    def colorlogColorizer(level: int, text: str) -> str:
        code = codes.get(level)
        return f"{code}{text}{reset}" if code else text

    return colorlogColorizer


class BlockFormatter(logging.Formatter):
    """Formatter, der mehrzeilige Befunde als eingerückten, abgesetzten Block ausgibt.

    Einzeilige Meldungen bleiben kompakt untereinander. Sobald eine Meldung
    mehrere Zeilen hat (die detaillierten Fehler- und Warnblöcke), werden die
    Folgezeilen eingerückt und der Block durch eine Leerzeile abgesetzt.
    """

    def __init__(self, colorizer: Colorizer) -> None:
        super().__init__(_LOG_FORMAT)
        self.colorizer = colorizer
        # Verhindert eine führende Leerzeile vor der allerersten Meldung.
        self._previousBlockSeparated = True

    def format(self, record: logging.LogRecord) -> str:
        record.location = f"{record.filename}:{record.lineno}"
        text = super().format(record)

        lines = text.split("\n")
        isBlock = len(lines) > 1
        if isBlock:
            text = ("\n" + CONTINUATION_INDENT).join(lines)

        body = self.colorizer(record.levelno, text)
        if not isBlock:
            self._previousBlockSeparated = False
            return body

        leading = "" if self._previousBlockSeparated else "\n"
        self._previousBlockSeparated = True
        return f"{leading}{body}\n"


def supportsColor(stream: object) -> bool:
    """Prüft, ob auf diesem Stream ANSI-Farben sinnvoll sind."""
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def buildFormatter(useColor: bool) -> logging.Formatter:
    """Erzeugt den Formatter samt passender Einfärbung."""
    return BlockFormatter(buildColorizer(useColor))


def configureLogging(level: int = logging.INFO, color: bool | None = None) -> logging.Logger:
    """Konfiguriert den Converter-Logger und liefert ihn zurück.

    Args:
        level: Minimales Log-Level.
        color: ``True``/``False`` erzwingt Farbe; ``None`` = automatisch nach TTY.
    """
    stream = sys.stderr
    useColor = supportsColor(stream) if color is None else color

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    for existing in list(logger.handlers):
        logger.removeHandler(existing)

    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    handler.setFormatter(buildFormatter(useColor))
    logger.addHandler(handler)
    return logger


def addDebugFileHandler(logger: logging.Logger, path: Path) -> Path:
    """Hängt einen zusätzlichen Handler an, der ALLES ab ``DEBUG`` in eine Datei schreibt.

    Unabhängig vom Konsolen-Log-Level (``--log-level``) landet im Debug-File immer
    die volle Detailtiefe – nützlich, um ein Problem nachträglich zu untersuchen,
    ohne die Konsole mit ``DEBUG``-Meldungen zu überfluten. Die Datei ist reiner
    Text ohne ANSI-Farbcodes, damit sie sich problemlos weitergeben und durchsuchen
    lässt. Eine bestehende Datei wird überschrieben, nicht angehängt.

    Returns:
        Der absolute Pfad der Debug-Datei (für die Abschlussmeldung).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, mode="w", encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(BlockFormatter(plainColorizer))
    logger.addHandler(handler)
    if logger.level > logging.DEBUG:
        logger.setLevel(logging.DEBUG)
    return path.resolve()


def getLogger(name: str | None = None) -> logging.Logger:
    """Liefert den Converter-Logger bzw. einen benannten Unterlogger."""
    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")
