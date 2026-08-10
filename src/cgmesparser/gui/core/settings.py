"""User preferences as a plain value.

Reading and writing them is the job of ``cgmesparser.gui.settingsStore``; this
module only describes what a valid set of preferences is, so the rules can be
tested without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

MIN_LOG_ROWS = 100
MAX_LOG_ROWS = 100_000
DEFAULT_LOG_ROWS = 5_000


@dataclass(frozen=True, slots=True)
class Preferences:
    """Everything the user can configure in the Preferences dialog."""

    rememberPaths: bool = True
    verboseLogging: bool = False
    maxLogRows: int = DEFAULT_LOG_ROWS
    confirmOnExit: bool = True
    openOutputWhenFinished: bool = False

    def normalised(self) -> Preferences:
        """Return a copy with out-of-range values pulled back into range.

        Preferences can come from a settings file edited by hand or written by
        an older version, so they are clamped rather than trusted.
        """
        return replace(self, maxLogRows=_clampLogRows(self.maxLogRows))


def _clampLogRows(value: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LOG_ROWS
    return max(MIN_LOG_ROWS, min(MAX_LOG_ROWS, number))
