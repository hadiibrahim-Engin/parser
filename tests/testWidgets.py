"""Widget behaviour, exercised headless through pytest-qt."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.result import ConversionOutcome, LogRecord, StageUpdate
from cgmesparser.gui.core.session import SessionInfo
from cgmesparser.gui.core.settings import Preferences
from cgmesparser.gui.core.states import (
    ORDERED_STAGES,
    ApplicationState,
    CheckStatus,
    InputRole,
    MessageLevel,
    ProcessingStage,
    StageState,
)
from cgmesparser.gui.core.transitions import buttonStatesFor
from cgmesparser.gui.core.validation import InputCheck, ValidationReport, validateRequest
from cgmesparser.gui.dialogs.preferences import PreferencesDialog
from cgmesparser.gui.widgets.actionBar import ActionBar
from cgmesparser.gui.widgets.common import EMPTY_VALUE
from cgmesparser.gui.widgets.inputSources import (
    InputSourcesCard,
    PathSelectorRow,
    ValidationStrip,
    droppedPath,
)
from cgmesparser.gui.widgets.messages import MessagesCard
from cgmesparser.gui.widgets.output import OutputCard
from cgmesparser.gui.widgets.processing import ProcessingCard, StageStepper
from cgmesparser.gui.widgets.session import SessionInfoCard


class TestPathSelectorRow:
    def testTypingAPathAnnouncesIt(self, qtbot) -> None:
        row = PathSelectorRow(InputRole.PROFILE_ZIP)
        qtbot.addWidget(row)
        with qtbot.waitSignal(row.pathChanged, timeout=2000) as caught:
            row._edit.setText("/data/profile.zip")
            row._edit.editingFinished.emit()
        assert caught.args[0] is InputRole.PROFILE_ZIP
        assert caught.args[1] == Path("/data/profile.zip")

    def testRestoringAPathIsSilent(self, qtbot) -> None:
        row = PathSelectorRow(InputRole.PROFILE_ZIP)
        qtbot.addWidget(row)
        with qtbot.assertNotEmitted(row.pathChanged):
            row.setPath(Path("/data/profile.zip"))
        assert row.path() == Path("/data/profile.zip")

    def testClearingTheTextYieldsNone(self, qtbot) -> None:
        row = PathSelectorRow(InputRole.SNAPSHOT_DATASET)
        qtbot.addWidget(row)
        row.setPath(Path("/data/snapshot"))
        with qtbot.waitSignal(row.pathChanged, timeout=2000) as caught:
            row._edit.setText("")
            row._edit.editingFinished.emit()
        assert caught.args[1] is None

    def testRepeatingTheSamePathDoesNotReannounce(self, qtbot) -> None:
        row = PathSelectorRow(InputRole.SNAPSHOT_DATASET)
        qtbot.addWidget(row)
        row.setPath(Path("/data/snapshot"))
        with qtbot.assertNotEmitted(row.pathChanged):
            row._edit.editingFinished.emit()

    def testDisablingLocksBothTheFieldAndTheButton(self, qtbot) -> None:
        row = PathSelectorRow(InputRole.PROFILE_ZIP)
        qtbot.addWidget(row)
        row.setEditable(False)
        assert row._edit.isEnabled() is False
        assert row._browse.isEnabled() is False


def urlMimeData(*paths: Path) -> QMimeData:
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    return data


class TestDroppedPath:
    """What a drop is understood to carry, decided in one place."""

    def testASingleLocalFileIsTaken(self, tmp_path: Path) -> None:
        target = tmp_path / "profile.zip"
        target.write_bytes(b"PK\x05\x06")
        assert droppedPath(urlMimeData(target)) == target

    def testADirectoryIsTakenToo(self, tmp_path: Path) -> None:
        assert droppedPath(urlMimeData(tmp_path)) == tmp_path

    def testTheKindOfPathIsNotJudgedHere(self, tmp_path: Path) -> None:
        # A folder dropped on the ZIP row is accepted and then reported by
        # validateRequest as "Not a file". The rule lives there, not here.
        assert droppedPath(urlMimeData(tmp_path)) is not None

    def testAPathNeedNotExist(self, tmp_path: Path) -> None:
        assert droppedPath(urlMimeData(tmp_path / "gone.zip")) is not None

    def testSeveralPathsAreRefused(self, tmp_path: Path) -> None:
        first, second = tmp_path / "a.zip", tmp_path / "b.zip"
        assert droppedPath(urlMimeData(first, second)) is None

    def testPlainTextIsRefused(self) -> None:
        data = QMimeData()
        data.setText("/data/profile.zip")
        assert droppedPath(data) is None

    def testARemoteUrlIsRefused(self) -> None:
        data = QMimeData()
        data.setUrls([QUrl("https://example.invalid/profile.zip")])
        assert droppedPath(data) is None

    def testEmptyMimeDataIsRefused(self) -> None:
        assert droppedPath(QMimeData()) is None


class TestPathSelectorRowDropping:
    def dropOn(self, row: PathSelectorRow, data: QMimeData) -> QDropEvent:
        event = QDropEvent(
            QPointF(10.0, 10.0),
            Qt.DropAction.CopyAction,
            data,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        row.dropEvent(event)
        return event

    def testDroppingAPathAnnouncesIt(self, qtbot, tmp_path: Path) -> None:
        row = PathSelectorRow(InputRole.PROFILE_ZIP)
        qtbot.addWidget(row)
        dropped = tmp_path / "profile.zip"
        dropped.write_bytes(b"PK\x05\x06")

        with qtbot.waitSignal(row.pathChanged, timeout=2000) as caught:
            self.dropOn(row, urlMimeData(dropped))

        assert caught.args[0] is InputRole.PROFILE_ZIP
        assert caught.args[1] == dropped
        assert row.path() == dropped

    def testDroppingShowsThePathInTheField(self, qtbot, tmp_path: Path) -> None:
        row = PathSelectorRow(InputRole.OUTPUT_DIRECTORY)
        qtbot.addWidget(row)
        self.dropOn(row, urlMimeData(tmp_path))
        assert row._edit.text() == str(tmp_path)

    def testADisabledRowRefusesDrops(self, qtbot, tmp_path: Path) -> None:
        row = PathSelectorRow(InputRole.PROFILE_ZIP)
        qtbot.addWidget(row)
        row.setEditable(False)
        with qtbot.assertNotEmitted(row.pathChanged):
            event = self.dropOn(row, urlMimeData(tmp_path / "profile.zip"))
        assert event.isAccepted() is False

    def testAnUnusableDropIsRefused(self, qtbot) -> None:
        row = PathSelectorRow(InputRole.PROFILE_ZIP)
        qtbot.addWidget(row)
        data = QMimeData()
        data.setText("not a url")
        with qtbot.assertNotEmitted(row.pathChanged):
            self.dropOn(row, data)

    def testTheFieldHighlightsWhileADragHovers(self, qtbot, tmp_path: Path) -> None:
        row = PathSelectorRow(InputRole.SNAPSHOT_DATASET)
        qtbot.addWidget(row)
        assert row._edit.property("dropActive") in (None, "false")

        row._setDropActive(True)
        assert row._edit.property("dropActive") == "true"

        row._setDropActive(False)
        assert row._edit.property("dropActive") == "false"

    def testTheHighlightIsClearedByTheDropItself(self, qtbot, tmp_path: Path) -> None:
        row = PathSelectorRow(InputRole.SNAPSHOT_DATASET)
        qtbot.addWidget(row)
        row._setDropActive(True)
        self.dropOn(row, urlMimeData(tmp_path))
        assert row._edit.property("dropActive") == "false"

    def testTheRowAcceptsDropsButTheFieldDoesNot(self, qtbot) -> None:
        # The line edit would otherwise swallow the drop and paste the URL.
        row = PathSelectorRow(InputRole.PROFILE_ZIP)
        qtbot.addWidget(row)
        assert row.acceptDrops() is True
        assert row._edit.acceptDrops() is False


class TestValidationStrip:
    def testStartsNeutral(self, qtbot) -> None:
        strip = ValidationStrip()
        qtbot.addWidget(strip)
        assert strip._verdict.text() == "Not validated"
        assert strip.property("tone") == "neutral"

    def testAValidReportReadsAsValidated(self, qtbot, validRequest: ConversionRequest) -> None:
        strip = ValidationStrip()
        qtbot.addWidget(strip)
        strip.applyReport(validateRequest(validRequest))
        assert strip._verdict.text() == "Inputs validated"
        assert strip.property("tone") == "ok"

    def testAnInvalidReportTurnsTheStripRed(self, qtbot) -> None:
        strip = ValidationStrip()
        qtbot.addWidget(strip)
        strip.applyReport(validateRequest(ConversionRequest()))
        assert strip.property("tone") == "error"

    def testOneEntryIsShownPerCheck(self, qtbot, validRequest: ConversionRequest) -> None:
        strip = ValidationStrip()
        qtbot.addWidget(strip)
        strip.applyReport(validateRequest(validRequest))
        assert len(strip._rows) == len(InputRole)

    def testApplyingASecondReportReplacesTheFirst(self, qtbot, validRequest: ConversionRequest) -> None:
        strip = ValidationStrip()
        qtbot.addWidget(strip)
        strip.applyReport(validateRequest(validRequest))
        strip.applyReport(ValidationReport((InputCheck(InputRole.PROFILE_ZIP, CheckStatus.OK, "OK"),)))
        assert len(strip._rows) == 1

    def testClearingReturnsToNeutral(self, qtbot, validRequest: ConversionRequest) -> None:
        strip = ValidationStrip()
        qtbot.addWidget(strip)
        strip.applyReport(validateRequest(validRequest))
        strip.clear()
        assert strip.property("tone") == "neutral"


class TestStageStepper:
    def testEveryStageStartsPending(self, qtbot) -> None:
        stepper = StageStepper()
        qtbot.addWidget(stepper)
        assert all(stepper.stageState(stage) is StageState.PENDING for stage in ORDERED_STAGES)

    def testOnlyOneStageIsEverActive(self, qtbot) -> None:
        stepper = StageStepper()
        qtbot.addWidget(stepper)
        stepper.setStageState(ProcessingStage.LOAD_MODELS, StageState.ACTIVE)
        stepper.setStageState(ProcessingStage.EXTRACT_LINES, StageState.ACTIVE)

        active = [s for s in ORDERED_STAGES if stepper.stageState(s) is StageState.ACTIVE]
        assert active == [ProcessingStage.EXTRACT_LINES]
        # the one it displaced is treated as finished, not abandoned
        assert stepper.stageState(ProcessingStage.LOAD_MODELS) is StageState.COMPLETED

    def testTheSpinnerRunsOnlyWhileSomethingIsActive(self, qtbot) -> None:
        stepper = StageStepper()
        qtbot.addWidget(stepper)
        assert stepper.isSpinning() is False

        stepper.setStageState(ProcessingStage.MERGE_DATA, StageState.ACTIVE)
        assert stepper.isSpinning() is True

        stepper.setStageState(ProcessingStage.MERGE_DATA, StageState.COMPLETED)
        assert stepper.isSpinning() is False

    def testResetClearsEverythingAndStopsTheTimer(self, qtbot) -> None:
        stepper = StageStepper()
        qtbot.addWidget(stepper)
        stepper.setStageState(ProcessingStage.MERGE_DATA, StageState.ACTIVE)
        stepper.reset()
        assert stepper.activeStage() is None
        assert stepper.isSpinning() is False

    def testAnUpdateObjectIsAccepted(self, qtbot) -> None:
        stepper = StageStepper()
        qtbot.addWidget(stepper)
        stepper.applyUpdate(StageUpdate(ProcessingStage.EXCEL_EXPORT, StageState.FAILED))
        assert stepper.stageState(ProcessingStage.EXCEL_EXPORT) is StageState.FAILED


class TestProcessingCard:
    @pytest.mark.parametrize(("given", "expected"), [(-20, 0), (0, 0), (62, 62), (140, 100)])
    def testProgressIsClamped(self, qtbot, given: int, expected: int) -> None:
        card = ProcessingCard()
        qtbot.addWidget(card)
        card.setProgress(given)
        assert card.progress() == expected
        assert card._progressLabel.text() == f"{expected}%"

    def testResetReturnsToIdle(self, qtbot) -> None:
        card = ProcessingCard()
        qtbot.addWidget(card)
        card.setProgress(80)
        card.setStatus("Working")
        card.applyStageUpdate(StageUpdate(ProcessingStage.MERGE_DATA, StageState.ACTIVE))
        card.reset()
        assert card.progress() == 0
        assert card.status() == "Idle"
        assert card.stepper.activeStage() is None


class TestMessagesCard:
    def testCountsAppearInTheTabTitles(self, qtbot) -> None:
        card = MessagesCard()
        qtbot.addWidget(card)
        card.append(LogRecord.now(MessageLevel.INFO, "started"))
        card.append(LogRecord.now(MessageLevel.WARNING, "directory exists"))
        card.append(LogRecord.now(MessageLevel.ERROR, "not implemented"))
        card.append(LogRecord.now(MessageLevel.ERROR, "also not implemented"))
        assert card.tabTitles() == ("Log", "Warnings (1)", "Errors (2)")

    def testEachTabFiltersToItsLevel(self, qtbot) -> None:
        card = MessagesCard()
        qtbot.addWidget(card)
        card.append(LogRecord.now(MessageLevel.INFO, "a"))
        card.append(LogRecord.now(MessageLevel.WARNING, "b"))
        card.append(LogRecord.now(MessageLevel.ERROR, "c"))
        assert card.visibleRowCount(None) == 3
        assert card.visibleRowCount(MessageLevel.WARNING) == 1
        assert card.visibleRowCount(MessageLevel.ERROR) == 1

    def testTheRingBufferDropsOldestFirst(self, qtbot) -> None:
        card = MessagesCard(maxRows=3)
        qtbot.addWidget(card)
        for index in range(6):
            card.append(LogRecord.now(MessageLevel.INFO, f"line {index}"))
        messages = [record.message for record in card.model.records()]
        assert messages == ["line 3", "line 4", "line 5"]
        assert card.visibleRowCount(None) == 3

    def testClearEmptiesTheModelAndTheCounts(self, qtbot) -> None:
        card = MessagesCard()
        qtbot.addWidget(card)
        card.append(LogRecord.now(MessageLevel.ERROR, "boom"))
        with qtbot.waitSignal(card.clearRequested, timeout=2000):
            card._clear.click()
        assert card.visibleRowCount(None) == 0
        assert card.tabTitles() == ("Log", "Warnings (0)", "Errors (0)")

    def testRaisingTheLimitKeepsExistingRows(self, qtbot) -> None:
        card = MessagesCard(maxRows=2)
        qtbot.addWidget(card)
        card.append(LogRecord.now(MessageLevel.INFO, "a"))
        card.append(LogRecord.now(MessageLevel.INFO, "b"))
        card.setMaxRows(10)
        assert card.visibleRowCount(None) == 2


class TestOutputCard:
    def testEveryValueStartsEmpty(self, qtbot) -> None:
        card = OutputCard()
        qtbot.addWidget(card)
        assert set(card.values().values()) == {EMPTY_VALUE}

    def testAnOutcomeFillsAllFourValues(self, qtbot, tmp_path: Path) -> None:
        card = OutputCard()
        qtbot.addWidget(card)
        card.applyOutcome(ConversionOutcome(tmp_path, 3, 1284, 146, datetime.now()))
        values = card.values()
        assert values["excelFiles"] == "3"
        assert values["detectedLines"] == "1,284"
        assert values["detectedSubstations"] == "146"
        assert values["lastRun"].startswith("Today, ")

    def testAnOlderRunIsDated(self, qtbot, tmp_path: Path) -> None:
        card = OutputCard()
        qtbot.addWidget(card)
        yesterday = datetime.now() - timedelta(days=1)
        card.applyOutcome(ConversionOutcome(tmp_path, 1, 2, 3, yesterday))
        assert card.values()["lastRun"].startswith(yesterday.strftime("%Y-%m-%d"))

    def testZeroIsShownAsZeroNotAsEmpty(self, qtbot) -> None:
        # A real run that found nothing must be distinguishable from no run.
        card = OutputCard()
        qtbot.addWidget(card)
        card.setDetectedLines(0)
        assert card.values()["detectedLines"] == "0"

    def testClearingReturnsToEmpty(self, qtbot, tmp_path: Path) -> None:
        card = OutputCard()
        qtbot.addWidget(card)
        card.applyOutcome(ConversionOutcome(tmp_path, 3, 1284, 146, datetime.now()))
        card.clear()
        assert set(card.values().values()) == {EMPTY_VALUE}


class TestSessionInfoCard:
    def testItShowsWhatWasCaptured(self, qtbot) -> None:
        card = SessionInfoCard()
        qtbot.addWidget(card)
        card.applySessionInfo(
            SessionInfo("2025-05-13_0814", "user", "ENG-LAPTOP-01", "3.12.13", "6.11.1")
        )
        assert card.values() == {
            "sessionId": "2025-05-13_0814",
            "user": "user",
            "computer": "ENG-LAPTOP-01",
            "pythonVersion": "3.12.13",
            "pysideVersion": "6.11.1",
        }


class TestActionBar:
    @pytest.mark.parametrize("state", list(ApplicationState))
    def testEnablementComesFromTheMatrix(self, qtbot, state: ApplicationState) -> None:
        bar = ActionBar()
        qtbot.addWidget(bar)
        states = buttonStatesFor(state, hasAllPaths=True, outputDirectoryExists=True)
        bar.applyButtonStates(states)
        assert bar.enabledStates() == {
            "preferences": states.preferences,
            "validate": states.validate,
            "start": states.start,
            "stop": states.stop,
            "exit": states.exit,
        }

    @pytest.mark.parametrize(
        ("name", "signalName"),
        [
            ("preferences", "preferencesRequested"),
            ("validate", "validateRequested"),
            ("start", "startRequested"),
            ("stop", "stopRequested"),
            ("exit", "exitRequested"),
        ],
    )
    def testEachButtonEmitsItsIntent(self, qtbot, name: str, signalName: str) -> None:
        bar = ActionBar()
        qtbot.addWidget(bar)
        button = bar.buttonFor(name)
        button.setEnabled(True)
        with qtbot.waitSignal(getattr(bar, signalName), timeout=2000):
            button.click()


class TestInputSourcesCard:
    def testItForwardsEveryRowsChanges(self, qtbot) -> None:
        card = InputSourcesCard()
        qtbot.addWidget(card)
        row = card.rowFor(InputRole.CIM_CACHE_DATASET)
        with qtbot.waitSignal(card.pathChanged, timeout=2000) as caught:
            row._edit.setText("/data/cache")
            row._edit.editingFinished.emit()
        assert caught.args[0] is InputRole.CIM_CACHE_DATASET

    def testApplyingARequestDoesNotEchoBack(self, qtbot, validRequest: ConversionRequest) -> None:
        card = InputSourcesCard()
        qtbot.addWidget(card)
        with qtbot.assertNotEmitted(card.pathChanged):
            card.applyRequest(validRequest)
        assert card.rowFor(InputRole.PROFILE_ZIP).path() == validRequest.profileZip


class TestPreferencesDialog:
    def testItLoadsTheGivenValues(self, qtbot) -> None:
        dialog = PreferencesDialog(Preferences(verboseLogging=True, maxLogRows=1234))
        qtbot.addWidget(dialog)
        assert dialog.preferences().verboseLogging is True
        assert dialog.preferences().maxLogRows == 1234

    def testEditsAreReturned(self, qtbot) -> None:
        dialog = PreferencesDialog(Preferences())
        qtbot.addWidget(dialog)
        dialog._rememberPaths.setChecked(False)
        dialog._maxLogRows.setValue(2500)
        result = dialog.preferences()
        assert result.rememberPaths is False
        assert result.maxLogRows == 2500

    def testRestoreDefaultsUndoesEdits(self, qtbot) -> None:
        dialog = PreferencesDialog(Preferences(rememberPaths=False, maxLogRows=999))
        qtbot.addWidget(dialog)
        dialog.restoreDefaults()
        assert dialog.preferences() == Preferences()

    def testTheDialogDoesNotWriteSettingsItself(self, qtbot, settingsStore) -> None:
        before = settingsStore.loadPreferences()
        dialog = PreferencesDialog(Preferences(maxLogRows=777))
        qtbot.addWidget(dialog)
        dialog._maxLogRows.setValue(888)
        assert settingsStore.loadPreferences() == before
