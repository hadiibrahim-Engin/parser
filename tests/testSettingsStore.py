"""Persistence, always against a temporary settings file."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.settings import DEFAULT_LOG_ROWS, MAX_LOG_ROWS, Preferences
from cgmesparser.gui.core.states import InputRole
from cgmesparser.gui.settingsStore import SettingsStore


class TestPreferencesRoundTrip:
    def testDefaultsComeBackFromAnEmptyStore(self, settingsStore: SettingsStore) -> None:
        assert settingsStore.loadPreferences() == Preferences()

    def testEveryFieldSurvivesARoundTrip(self, settingsStore: SettingsStore) -> None:
        saved = Preferences(
            rememberPaths=False,
            verboseLogging=True,
            maxLogRows=2500,
            confirmOnExit=False,
            openOutputWhenFinished=True,
        )
        settingsStore.savePreferences(saved)
        assert settingsStore.loadPreferences() == saved

    def testValuesAreClampedOnTheWayOut(self, tmp_path: Path) -> None:
        settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
        settings.setValue("preferences/maxLogRows", 10**9)
        settings.sync()
        assert SettingsStore(settings).loadPreferences().maxLogRows == MAX_LOG_ROWS

    def testAHandEditedGarbageValueFallsBackToTheDefault(self, tmp_path: Path) -> None:
        settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
        settings.setValue("preferences/maxLogRows", "lots")
        settings.sync()
        assert SettingsStore(settings).loadPreferences().maxLogRows == DEFAULT_LOG_ROWS

    def testBooleansSurviveBeingStoredAsStrings(self, tmp_path: Path) -> None:
        settings = QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat)
        settings.setValue("preferences/verboseLogging", "true")
        settings.sync()
        assert SettingsStore(settings).loadPreferences().verboseLogging is True


class TestRequestRoundTrip:
    def testExistingPathsAreRestored(self, settingsStore: SettingsStore, validRequest) -> None:
        settingsStore.saveRequest(validRequest)
        assert settingsStore.loadRequest() == validRequest

    def testAPathThatHasSinceDisappearedIsDropped(
        self, settingsStore: SettingsStore, validRequest, tmp_path: Path
    ) -> None:
        # Opening the window showing a path that no longer exists would be a lie
        # about the state of the machine.
        settingsStore.saveRequest(validRequest)
        validRequest.profileZip.unlink()
        restored = settingsStore.loadRequest()
        assert restored.profileZip is None
        assert restored.snapshotDataset == validRequest.snapshotDataset

    def testNothingIsRestoredWhenRememberingIsOff(
        self, settingsStore: SettingsStore, validRequest
    ) -> None:
        settingsStore.saveRequest(validRequest)
        assert settingsStore.loadRequest(rememberPaths=False) == ConversionRequest()

    def testForgettingClearsEveryStoredPath(self, settingsStore: SettingsStore, validRequest) -> None:
        settingsStore.saveRequest(validRequest)
        settingsStore.forgetPaths()
        assert settingsStore.loadRequest() == ConversionRequest()

    def testAnUnsetRoleIsStoredAsEmpty(self, settingsStore: SettingsStore, validRequest) -> None:
        settingsStore.saveRequest(validRequest.withPath(InputRole.PROFILE_ZIP, None))
        assert settingsStore.loadRequest().profileZip is None


class TestWindowState:
    def testNothingIsReturnedBeforeAnythingIsSaved(self, settingsStore: SettingsStore) -> None:
        assert settingsStore.loadGeometry() is None
        assert settingsStore.loadWindowState() is None

    def testGeometrySurvivesARoundTrip(self, settingsStore: SettingsStore, qtbot) -> None:
        from PySide6.QtWidgets import QMainWindow

        window = QMainWindow()
        qtbot.addWidget(window)
        window.resize(1200, 800)

        settingsStore.saveGeometry(window.saveGeometry())
        settingsStore.sync()

        restored = settingsStore.loadGeometry()
        assert restored is not None
        assert window.restoreGeometry(restored) is True
