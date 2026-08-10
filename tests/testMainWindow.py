"""End-to-end wiring: the window, its controller and the default backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from cgmesparser.gui.app import buildService, buildWindow, createApplication
from cgmesparser.gui.controller.conversion import ConversionController
from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.result import LogRecord
from cgmesparser.gui.core.session import SessionInfo
from cgmesparser.gui.core.settings import Preferences
from cgmesparser.gui.core.states import ApplicationState, InputRole, MessageLevel
from cgmesparser.gui.mainWindow import MainWindow
from cgmesparser.gui.services.unimplemented import NOT_IMPLEMENTED_MESSAGE, UnimplementedConversionService
from cgmesparser.gui.settingsStore import SettingsStore
from cgmesparser.gui.widgets.common import EMPTY_VALUE

TIMEOUT = 5000


@pytest.fixture
def window(qtbot, settingsStore: SettingsStore, validRequest: ConversionRequest) -> MainWindow:
    createApplication([])
    controller = ConversionController(UnimplementedConversionService(), validRequest)
    built = MainWindow(
        controller=controller,
        settingsStore=settingsStore,
        sessionInfo=SessionInfo.capture("6.11.1"),
        preferences=Preferences(),
        # Answer every confirmation instead of opening a modal dialog. Without
        # this, teardown of any test that re-enables confirmOnExit would block
        # the whole suite waiting for a click that can never come.
        confirm=lambda title, question: True,
    )
    qtbot.addWidget(built)
    return built


class TestAssembly:
    def testEveryCardIsPresent(self, window: MainWindow) -> None:
        assert window.inputsCard is not None
        assert window.processingCard is not None
        assert window.messagesCard is not None
        assert window.outputCard is not None
        assert window.sessionCard is not None
        assert window.actionBar is not None

    def testTheTitleIsTheProductName(self, window: MainWindow) -> None:
        assert window.windowTitle() == "CGMES MJAP Interface"

    def testTheOutputCardIsEmptyBeforeAnyRun(self, window: MainWindow) -> None:
        assert set(window.outputCard.values().values()) == {EMPTY_VALUE}

    def testSessionInfoIsFilledIn(self, window: MainWindow) -> None:
        assert window.sessionCard.values()["pysideVersion"] == "6.11.1"

    def testRestoredPathsAreShown(self, window: MainWindow, validRequest: ConversionRequest) -> None:
        assert window.rowFor(InputRole.PROFILE_ZIP).path() == validRequest.profileZip


class TestValidationFlow:
    def testValidatingRendersTheStripAndUnlocksStart(self, qtbot, window: MainWindow) -> None:
        window.actionBar.buttonFor("validate").click()
        assert window.actionBar.enabledStates()["start"] is True
        assert window.inputsCard._strip._verdict.text() == "Inputs validated"

    def testTheDirectoryExistsWarningReachesTheLog(self, qtbot, window: MainWindow) -> None:
        window.actionBar.buttonFor("validate").click()
        messages = [record.message for record in window.messagesCard.model.records()]
        assert any("Directory exists" in message for message in messages)

    def testChangingAPathClearsTheStripAndRelocksStart(self, qtbot, window: MainWindow) -> None:
        window.actionBar.buttonFor("validate").click()
        assert window.actionBar.enabledStates()["start"] is True

        row = window.rowFor(InputRole.SNAPSHOT_DATASET)
        row._edit.setText("/somewhere/else")
        row._edit.editingFinished.emit()

        assert window.actionBar.enabledStates()["start"] is False
        assert window.inputsCard._strip._verdict.text() == "Not validated"


class TestConversionFlow:
    def testStartingWithTheDefaultBackendFailsHonestly(self, qtbot, window: MainWindow) -> None:
        """The whole mechanism runs; it simply has nothing to run yet."""
        window.actionBar.buttonFor("validate").click()
        window.actionBar.buttonFor("start").click()

        qtbot.waitUntil(
            lambda: window._controller.state is ApplicationState.FAILED, timeout=TIMEOUT
        )
        errors = [
            record.message
            for record in window.messagesCard.model.records()
            if record.level is MessageLevel.ERROR
        ]
        assert NOT_IMPLEMENTED_MESSAGE in errors
        assert window.messagesCard.visibleRowCount(MessageLevel.ERROR) >= 1

    def testNoOutcomeMeansTheOutputCardStaysEmpty(self, qtbot, window: MainWindow) -> None:
        window.actionBar.buttonFor("validate").click()
        window.actionBar.buttonFor("start").click()
        qtbot.waitUntil(
            lambda: window._controller.state is ApplicationState.FAILED, timeout=TIMEOUT
        )
        assert set(window.outputCard.values().values()) == {EMPTY_VALUE}


class TestPreferences:
    def testApplyingPreferencesPersistsThem(
        self, window: MainWindow, settingsStore: SettingsStore
    ) -> None:
        window.applyPreferences(Preferences(maxLogRows=321, verboseLogging=True))
        assert settingsStore.loadPreferences().maxLogRows == 321
        assert window.preferences.verboseLogging is True

    def testTurningOffRememberPathsForgetsThem(
        self, window: MainWindow, settingsStore: SettingsStore
    ) -> None:
        window.applyPreferences(Preferences(rememberPaths=False))
        assert settingsStore.loadRequest() == ConversionRequest()

    def testTheLogLimitIsAppliedToTheCard(self, window: MainWindow) -> None:
        window.applyPreferences(Preferences(maxLogRows=100))
        for index in range(150):
            window.messagesCard.append(LogRecord.now(MessageLevel.INFO, f"line {index}"))
        assert window.messagesCard.visibleRowCount(None) == 100


class TestClosing:
    def testClosingPersistsGeometryAndPaths(
        self, window: MainWindow, settingsStore: SettingsStore, validRequest: ConversionRequest
    ) -> None:
        window.show()
        assert window.close() is True
        assert settingsStore.loadGeometry() is not None
        assert settingsStore.loadRequest() == validRequest


class TestComposition:
    def testTheDefaultServiceIsTheUnimplementedOne(self) -> None:
        assert isinstance(buildService(demo=False), UnimplementedConversionService)

    def testDemoModeIsOnlyReachableOnRequest(self) -> None:
        from cgmesparser.gui.services.demo import DemoConversionService

        assert isinstance(buildService(demo=True), DemoConversionService)

    def testBuildWindowWiresEverythingTogether(self, qtbot, tmp_path: Path) -> None:
        from PySide6.QtCore import QSettings

        createApplication([])
        store = SettingsStore(QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat))
        # buildWindow uses the real message-box confirmation, so the exit prompt
        # is switched off in the store before the window reads its preferences.
        store.savePreferences(Preferences(confirmOnExit=False))

        built = buildWindow(buildService(demo=False), store)
        qtbot.addWidget(built)
        assert built.messagesCard.visibleRowCount(None) >= 1
        assert built.preferences.confirmOnExit is False
