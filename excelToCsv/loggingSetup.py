"""Farbiges, strukturiertes Konsolen-Logging.

Nutzt ``colorlog``, falls installiert; andernfalls greift ein schlanker
ANSI-Fallback. Der Converter gibt Status-, Warn- und Fehlermeldungen
ausschließlich über ``logging`` aus – niemals über ``print()``.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Final

LOGGER_NAME: Final = "excelToCsv"

_LOG_FORMAT: Final = "%(levelname)-8s %(message)s"

#: Farbzuordnung je Level (colorlog-Syntax).
_COLORLOG_COLORS: Final[dict[str, str]] = {
    "DEBUG": "thin_white",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_white,bg_red",
}

#: ANSI-Fallback je Level.
_ANSI_COLORS: Final[dict[int, str]] = {
    logging.DEBUG: "\033[2;37m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[1;97;41m",
}
_ANSI_RESET: Final = "\033[0m"


class AnsiColorFormatter(logging.Formatter):
    """Minimaler farbiger Formatter, falls ``colorlog`` nicht verfügbar ist."""

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        color = _ANSI_COLORS.get(record.levelno)
        return f"{color}{text}{_ANSI_RESET}" if color else text


def supportsColor(stream: object) -> bool:
    """Prüft, ob auf diesem Stream ANSI-Farben sinnvoll sind."""
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def buildFormatter(useColor: bool) -> logging.Formatter:
    """Erzeugt den passenden Formatter (colorlog, ANSI-Fallback oder farblos)."""
    if not useColor:
        return logging.Formatter(_LOG_FORMAT)
    try:
        import colorlog
    except ImportError:
        return AnsiColorFormatter(_LOG_FORMAT)
    return colorlog.ColoredFormatter(
        "%(log_color)s" + _LOG_FORMAT,
        log_colors=_COLORLOG_COLORS,
    )


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


def getLogger(name: str | None = None) -> logging.Logger:
    """Liefert den Converter-Logger bzw. einen benannten Unterlogger."""
    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")
