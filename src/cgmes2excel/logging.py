"""Colour-aware console logging plus clean, colourless log files."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

SUCCESS = logging.INFO + 5
logging.addLevelName(SUCCESS, "OK")

_RESET = "\x1b[0m"
_COLOURS = {
    logging.DEBUG: "\x1b[2;37m",
    logging.INFO: "\x1b[36m",
    SUCCESS: "\x1b[32m",
    logging.WARNING: "\x1b[33m",
    logging.ERROR: "\x1b[31m",
    logging.CRITICAL: "\x1b[1;91m",
}
_TAGS = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    SUCCESS: "OK",
    logging.WARNING: "WARN",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRIT",
}


class CgmesLogger(logging.Logger):
    """Logger with the extra ``success`` level used for milestone messages."""

    def success(self, message: str, *args: object, **kwargs: object) -> None:
        if self.isEnabledFor(SUCCESS):
            self._log(SUCCESS, message, args, **kwargs)  # type: ignore[arg-type]


logging.setLoggerClass(CgmesLogger)


def getLogger(name: str = "cgmes2excel") -> CgmesLogger:
    logger = logging.getLogger(name)
    if not isinstance(logger, CgmesLogger):  # a plain Logger was created earlier
        logger.__class__ = CgmesLogger
    return logger  # type: ignore[return-value]


class ConsoleFormatter(logging.Formatter):
    """``[LEVEL] message``, optionally coloured for a capable terminal."""

    def __init__(self, useColour: bool = True) -> None:
        super().__init__()
        self.useColour = useColour

    def format(self, record: logging.LogRecord) -> str:
        tag = _TAGS.get(record.levelno, record.levelname)
        message = record.getMessage()
        if record.exc_info:
            message = f"{message}\n{self.formatException(record.exc_info)}"
        if not self.useColour:
            return f"[{tag}] {message}"
        colour = _COLOURS.get(record.levelno, "")
        return f"{colour}[{tag}]{_RESET} {colour}{message}{_RESET}"


class PlainFormatter(logging.Formatter):
    """Structured, never-coloured output for log files."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )


def supportsColour(stream: object = None) -> bool:
    """Whether ANSI colour should be used for ``stream``."""
    stream = stream if stream is not None else sys.stderr
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


def configureLogging(
    verbose: bool = False,
    colour: bool | None = None,
    logFile: Path | None = None,
    stream: object = None,
) -> CgmesLogger:
    """Install the console (and optional file) handlers on the root logger."""
    stream = stream if stream is not None else sys.stderr
    useColour = supportsColour(stream) if colour is None else colour

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    console = logging.StreamHandler(stream)  # type: ignore[arg-type]
    console.setFormatter(ConsoleFormatter(useColour=useColour))
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.addHandler(console)

    if logFile is not None:
        logFile.parent.mkdir(parents=True, exist_ok=True)
        fileHandler = logging.FileHandler(logFile, mode="w", encoding="utf-8")
        fileHandler.setFormatter(PlainFormatter())
        fileHandler.setLevel(logging.DEBUG if verbose else logging.INFO)
        root.addHandler(fileHandler)

    return getLogger()
