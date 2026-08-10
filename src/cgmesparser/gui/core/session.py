"""A snapshot of the environment, shown in the Session Info card."""

from __future__ import annotations

import getpass
import platform
from dataclasses import dataclass
from datetime import datetime

_UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """Identifies this run of the application for support and log correlation."""

    sessionId: str
    user: str
    computer: str
    pythonVersion: str
    pysideVersion: str

    @classmethod
    def capture(cls, pysideVersion: str, now: datetime | None = None) -> SessionInfo:
        """Read the current environment.

        ``pysideVersion`` is passed in rather than imported so that this module,
        like the rest of ``core``, stays free of Qt.
        """
        moment = now if now is not None else datetime.now()
        return cls(
            sessionId=moment.strftime("%Y-%m-%d_%H%M"),
            user=_currentUser(),
            computer=_computerName(),
            pythonVersion=platform.python_version(),
            pysideVersion=pysideVersion or _UNKNOWN,
        )


def _currentUser() -> str:
    try:
        return getpass.getuser() or _UNKNOWN
    except (OSError, KeyError):
        # getuser() consults the environment and then the password database;
        # both can fail on a locked-down or containerised host.
        return _UNKNOWN


def _computerName() -> str:
    try:
        return platform.node() or _UNKNOWN
    except OSError:
        return _UNKNOWN
