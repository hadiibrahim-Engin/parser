"""Persistence of paths, window geometry and preferences.

This is the only module that touches ``QSettings``. It sits outside ``core``
because ``QSettings`` is Qt, and ``core`` is deliberately Qt-free; what a valid
set of preferences *is* lives in :mod:`cgmesparser.gui.core.settings`.

The ``QSettings`` instance is injected rather than constructed here, so tests
point it at a temporary file instead of the developer's real registry.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.settings import Preferences
from cgmesparser.gui.core.states import ORDERED_ROLES, InputRole
from cgmesparser.gui.version import APPLICATION_NAME, ORGANISATION_NAME

_PATH_KEY = {
    InputRole.PROFILE_ZIP: "paths/profileZip",
    InputRole.SNAPSHOT_DATASET: "paths/snapshotDataset",
    InputRole.CIM_CACHE_DATASET: "paths/cimCacheDataset",
    InputRole.OUTPUT_DIRECTORY: "paths/outputDirectory",
}

_GEOMETRY_KEY = "window/geometry"
_STATE_KEY = "window/state"

_PREFERENCE_KEYS = {
    "rememberPaths": "preferences/rememberPaths",
    "verboseLogging": "preferences/verboseLogging",
    "maxLogRows": "preferences/maxLogRows",
    "confirmOnExit": "preferences/confirmOnExit",
    "openOutputWhenFinished": "preferences/openOutputWhenFinished",
}


def defaultSettings() -> QSettings:
    """The real, per-user settings location for this application."""
    return QSettings(ORGANISATION_NAME, APPLICATION_NAME)


class SettingsStore:
    """Typed access to persisted state.

    Every read falls back to a default rather than raising: settings files get
    hand-edited and survive across versions, so they are treated as untrusted
    input.
    """

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings if settings is not None else defaultSettings()

    @property
    def settings(self) -> QSettings:
        return self._settings

    def sync(self) -> None:
        self._settings.sync()

    # -- preferences ----------------------------------------------------------

    def loadPreferences(self) -> Preferences:
        defaults = Preferences()
        return Preferences(
            rememberPaths=self._bool(_PREFERENCE_KEYS["rememberPaths"], defaults.rememberPaths),
            verboseLogging=self._bool(_PREFERENCE_KEYS["verboseLogging"], defaults.verboseLogging),
            maxLogRows=self._int(_PREFERENCE_KEYS["maxLogRows"], defaults.maxLogRows),
            confirmOnExit=self._bool(_PREFERENCE_KEYS["confirmOnExit"], defaults.confirmOnExit),
            openOutputWhenFinished=self._bool(
                _PREFERENCE_KEYS["openOutputWhenFinished"], defaults.openOutputWhenFinished
            ),
        ).normalised()

    def savePreferences(self, preferences: Preferences) -> None:
        normalised = preferences.normalised()
        for field, key in _PREFERENCE_KEYS.items():
            self._settings.setValue(key, getattr(normalised, field))
        self._settings.sync()

    # -- paths ----------------------------------------------------------------

    def loadRequest(self, rememberPaths: bool = True) -> ConversionRequest:
        """Restore the last used paths.

        A remembered path that has since disappeared is dropped rather than
        restored, so the interface never opens showing something that is gone.
        """
        request = ConversionRequest()
        if not rememberPaths:
            return request
        for role in ORDERED_ROLES:
            raw = self._settings.value(_PATH_KEY[role], "", type=str)
            if not raw:
                continue
            candidate = Path(raw)
            if candidate.exists():
                request = request.withPath(role, candidate)
        return request

    def saveRequest(self, request: ConversionRequest) -> None:
        for role in ORDERED_ROLES:
            path = request.pathFor(role)
            self._settings.setValue(_PATH_KEY[role], str(path) if path is not None else "")
        self._settings.sync()

    def forgetPaths(self) -> None:
        for key in _PATH_KEY.values():
            self._settings.remove(key)
        self._settings.sync()

    # -- window ---------------------------------------------------------------

    def loadGeometry(self) -> QByteArray | None:
        return self._byteArray(_GEOMETRY_KEY)

    def saveGeometry(self, geometry: QByteArray) -> None:
        self._settings.setValue(_GEOMETRY_KEY, geometry)

    def loadWindowState(self) -> QByteArray | None:
        return self._byteArray(_STATE_KEY)

    def saveWindowState(self, state: QByteArray) -> None:
        self._settings.setValue(_STATE_KEY, state)

    # -- coercion -------------------------------------------------------------

    def _bool(self, key: str, fallback: bool) -> bool:
        value = self._settings.value(key, fallback)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        try:
            return bool(int(value))
        except (TypeError, ValueError):
            return fallback

    def _int(self, key: str, fallback: int) -> int:
        value = self._settings.value(key, fallback)
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    def _byteArray(self, key: str) -> QByteArray | None:
        value = self._settings.value(key)
        return value if isinstance(value, QByteArray) and not value.isEmpty() else None
