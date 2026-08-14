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

#: Width of the source location (``reader.py:120``) inside the log line.
LOCATION_WIDTH: Final = 22

#: ``%(levelname)-8s`` plus separator - continuation lines align with it.
CONTINUATION_INDENT: Final = " " * 9

_LOG_FORMAT: Final = f"%(levelname)-8s %(location)-{LOCATION_WIDTH}s %(message)s"

#: Color names per level (colorlog notation).
_COLOR_NAMES: Final[dict[int, str]] = {
    logging.DEBUG: "thin_white",
    logging.INFO: "green",
    logging.WARNING: "yellow",
    logging.ERROR: "red",
    logging.CRITICAL: "bold_white,bg_red",
}

#: ANSI fallback per level, used when ``colorlog`` is unavailable.
_ANSI_COLORS: Final[dict[int, str]] = {
    logging.DEBUG: "\033[2;37m",
    logging.INFO: "\033[32m",
    logging.WARNING: "\033[33m",
    logging.ERROR: "\033[31m",
    logging.CRITICAL: "\033[1;97;41m",
}
_ANSI_RESET: Final = "\033[0m"

#: Signature of a colorizing function: (level, text) -> colorized text.
Colorizer = Callable[[int, str], str]


def plainColorizer(level: int, text: str) -> str:
    """Return the text unchanged (colors disabled)."""
    return text


def ansiColorizer(level: int, text: str) -> str:
    """Colorize the text using a minimal, built-in ANSI palette."""
    color = _ANSI_COLORS.get(level)
    return f"{color}{text}{_ANSI_RESET}" if color else text


def buildColorizer(useColor: bool) -> Colorizer:
    """Choose the colorizer: ``colorlog`` palette, ANSI fallback, or none."""
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
    """Formatter that renders multi-line findings as an indented, separated block.

    Single-line messages stay compact underneath each other. As soon as a
    message spans several lines (the detailed error and warning blocks), its
    continuation lines are indented and the block is set off by a blank line.
    """

    def __init__(self, colorizer: Colorizer) -> None:
        super().__init__(_LOG_FORMAT)
        self.colorizer = colorizer
        # Prevents a leading blank line in front of the very first message.
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
    """Check whether ANSI colors make sense on this stream."""
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


def buildFormatter(useColor: bool) -> logging.Formatter:
    """Build the formatter together with its colorizer."""
    return BlockFormatter(buildColorizer(useColor))


def configureLogging(level: int = logging.INFO, color: bool | None = None) -> logging.Logger:
    """Configure the converter logger and return it.

    Args:
        level: Minimum log level.
        color: ``True``/``False`` forces colors; ``None`` decides by TTY.
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
    """Attach an extra handler that writes EVERYTHING from ``DEBUG`` up to a file.

    Independent of the console log level (``--log-level``), the debug file always
    receives the full detail - useful to investigate a problem afterwards without
    flooding the console with ``DEBUG`` messages. The file is plain text without
    ANSI color codes so it can be shared and searched easily. An existing file is
    overwritten, not appended to.

    Returns:
        The absolute path of the debug file (for the closing message).
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
    """Return the converter logger, or a named child logger."""
    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")
