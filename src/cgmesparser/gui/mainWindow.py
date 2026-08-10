"""The main window: assembly and signal wiring, and nothing else.

This module builds the layout, connects the controller to the cards, and
persists window state. It contains no rules - which button is enabled, whether
a path is valid, and what state follows what are all decided in ``core`` and
delivered here as already-made decisions.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cgmesparser.gui.controller.conversion import ConversionController
from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.result import ConversionOutcome, LogRecord, StageUpdate
from cgmesparser.gui.core.session import SessionInfo
from cgmesparser.gui.core.settings import Preferences
from cgmesparser.gui.core.states import ApplicationState, InputRole, MessageLevel
from cgmesparser.gui.core.transitions import ButtonStates
from cgmesparser.gui.core.validation import ValidationReport
from cgmesparser.gui.dialogs.preferences import PreferencesDialog
from cgmesparser.gui.resources.tokens import TOKENS, Tokens
from cgmesparser.gui.settingsStore import SettingsStore
from cgmesparser.gui.version import APPLICATION_NAME
from cgmesparser.gui.widgets.actionBar import ActionBar
from cgmesparser.gui.widgets.header import HeaderBanner
from cgmesparser.gui.widgets.inputSources import InputSourcesCard
from cgmesparser.gui.widgets.messages import MessagesCard
from cgmesparser.gui.widgets.output import OutputCard
from cgmesparser.gui.widgets.processing import ProcessingCard
from cgmesparser.gui.widgets.session import SessionInfoCard

SUBTITLE = "Convert CGMES datasets into validated Excel workbooks"

_DEFAULT_SIZE = QSize(1420, 980)
_MINIMUM_SIZE = QSize(1100, 760)
_LEFT_COLUMN_MINIMUM = 670
_RIGHT_COLUMN_MINIMUM = 310


class MainWindow(QMainWindow):
    """The single window of the application."""

    def __init__(
        self,
        controller: ConversionController,
        settingsStore: SettingsStore,
        sessionInfo: SessionInfo,
        preferences: Preferences | None = None,
        tokens: Tokens = TOKENS,
        confirm: Callable[[str, str], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._store = settingsStore
        self._preferences = (preferences if preferences is not None else Preferences()).normalised()
        self._tokens = tokens
        # Injectable so a headless test can never block on a modal dialog.
        self._confirm = confirm if confirm is not None else self._askWithMessageBox

        self.setWindowTitle(APPLICATION_NAME)
        self.setMinimumSize(_MINIMUM_SIZE)
        self.resize(_DEFAULT_SIZE)

        self._buildLayout()
        self._connectWidgets()
        self._connectController()

        self._session.applySessionInfo(sessionInfo)
        self._messages.setMaxRows(self._preferences.maxLogRows)
        self._restoreWindowState()

        self._controller.emitCurrentState()

    # -- construction ---------------------------------------------------------

    def _buildLayout(self) -> None:
        root = QWidget(self)
        root.setObjectName("rootSurface")
        rootLayout = QVBoxLayout(root)
        rootLayout.setContentsMargins(0, 0, 0, 0)
        rootLayout.setSpacing(0)

        self._header = HeaderBanner(APPLICATION_NAME, SUBTITLE, self._tokens, root)
        rootLayout.addWidget(self._header)

        # A scroll area keeps every card reachable when the window is made
        # smaller than the content's natural height.
        scroll = QScrollArea(root)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content = QWidget(scroll)
        content.setObjectName("workspaceSurface")
        grid = QGridLayout(content)
        grid.setContentsMargins(24, 22, 24, 22)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)

        self._inputs = InputSourcesCard(self._tokens, content)
        self._processing = ProcessingCard(self._tokens, content)
        self._messages = MessagesCard(self._preferences.maxLogRows, self._tokens, content)
        self._output = OutputCard(self._tokens, content)
        self._session = SessionInfoCard(self._tokens, content)

        grid.addWidget(self._inputs, 0, 0)
        grid.addWidget(self._processing, 1, 0)
        grid.addWidget(self._messages, 2, 0)

        rail = QWidget(content)
        rail.setObjectName("contextRail")
        railLayout = QVBoxLayout(rail)
        railLayout.setContentsMargins(0, 0, 0, 0)
        railLayout.setSpacing(16)
        railLayout.addWidget(self._output)
        railLayout.addWidget(self._session)
        railLayout.addStretch(1)
        grid.addWidget(rail, 0, 1, 3, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 0)
        grid.setColumnMinimumWidth(0, _LEFT_COLUMN_MINIMUM)
        grid.setColumnMinimumWidth(1, _RIGHT_COLUMN_MINIMUM)
        grid.setRowStretch(2, 1)

        scroll.setWidget(content)
        rootLayout.addWidget(scroll, 1)

        self._actions = ActionBar(self._tokens, root)
        rootLayout.addWidget(self._actions)

        self.setCentralWidget(root)

    def _connectWidgets(self) -> None:
        self._inputs.pathChanged.connect(self._controller.setPath)
        self._actions.preferencesRequested.connect(self.openPreferences)
        self._actions.validateRequested.connect(self._controller.validateInputs)
        self._actions.startRequested.connect(self._controller.startConversion)
        self._actions.stopRequested.connect(self._controller.stopConversion)
        self._actions.exitRequested.connect(self.close)
        self._output.openFolderRequested.connect(self._controller.openOutputFolder)

    def _connectController(self) -> None:
        self._controller.requestChanged.connect(self._onRequestChanged)
        self._controller.validationCompleted.connect(self._onValidationCompleted)
        self._controller.validationCleared.connect(self._inputs.clearReport)
        self._controller.buttonStatesChanged.connect(self._onButtonStates)
        self._controller.stateChanged.connect(self._onStateChanged)
        self._controller.messageLogged.connect(self._onMessage)
        self._controller.stageChanged.connect(self._onStage)
        self._controller.progressChanged.connect(self._processing.setProgress)
        self._controller.statusChanged.connect(self._processing.setStatus)
        self._controller.outcomeReady.connect(self._onOutcome)
        self._controller.runStarted.connect(self._processing.reset)

    # -- controller callbacks -------------------------------------------------

    def _onRequestChanged(self, request: ConversionRequest) -> None:
        self._inputs.applyRequest(request)
        if self._preferences.rememberPaths:
            self._store.saveRequest(request)

    def _onValidationCompleted(self, report: ValidationReport) -> None:
        self._inputs.applyReport(report)

    def _onButtonStates(self, states: ButtonStates) -> None:
        self._actions.applyButtonStates(states)
        self._output.setOpenFolderEnabled(states.openOutputFolder)
        self._inputs.setEditable(states.inputsEditable)

    def _onStateChanged(self, state: ApplicationState) -> None:
        if state is ApplicationState.IDLE:
            self._processing.setStatus("Idle")

    def _onMessage(self, record: LogRecord) -> None:
        # Every record is kept. "Verbose logging" controls how much detail the
        # backend is asked to produce, not what the log is allowed to show.
        self._messages.append(record)

    def _onStage(self, update: StageUpdate) -> None:
        self._processing.applyStageUpdate(update)

    def _onOutcome(self, outcome: ConversionOutcome) -> None:
        self._output.applyOutcome(outcome)
        if self._preferences.openOutputWhenFinished:
            self._controller.openOutputFolder()

    # -- actions --------------------------------------------------------------

    def openPreferences(self) -> None:
        dialog = PreferencesDialog(self._preferences, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.applyPreferences(dialog.preferences())

    def applyPreferences(self, preferences: Preferences) -> None:
        """Adopt a new set of preferences and persist them."""
        previous = self._preferences
        self._preferences = preferences.normalised()
        self._store.savePreferences(self._preferences)
        self._messages.setMaxRows(self._preferences.maxLogRows)

        if previous.rememberPaths and not self._preferences.rememberPaths:
            self._store.forgetPaths()
        elif self._preferences.rememberPaths:
            self._store.saveRequest(self._controller.request)

        self._controller.log(MessageLevel.INFO, "Preferences updated.")

    # -- window lifecycle -----------------------------------------------------

    def _restoreWindowState(self) -> None:
        geometry = self._store.loadGeometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self._store.loadWindowState()
        if state is not None:
            self.restoreState(state)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Confirm, cancel any run, and wait for the thread before closing."""
        if self._controller.state.isBusy and self._controller.state is not ApplicationState.VALIDATING:
            if not self._confirmCloseDuringRun():
                event.ignore()
                return
        elif self._preferences.confirmOnExit and not self._confirmExit():
            event.ignore()
            return

        self._store.saveGeometry(self.saveGeometry())
        self._store.saveWindowState(self.saveState())
        if self._preferences.rememberPaths:
            self._store.saveRequest(self._controller.request)
        self._store.savePreferences(self._preferences)
        self._store.sync()

        self._controller.shutdown()
        event.accept()

    def _confirmCloseDuringRun(self) -> bool:
        return self._confirm(
            "Conversion in progress",
            "A conversion is still running.\n\nStop it and close the application?",
        )

    def _confirmExit(self) -> bool:
        return self._confirm("Exit", f"Close {APPLICATION_NAME}?")

    def _askWithMessageBox(self, title: str, question: str) -> bool:
        answer = QMessageBox.question(
            self,
            title,
            question,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    # -- introspection for tests ----------------------------------------------

    @property
    def inputsCard(self) -> InputSourcesCard:
        return self._inputs

    @property
    def processingCard(self) -> ProcessingCard:
        return self._processing

    @property
    def messagesCard(self) -> MessagesCard:
        return self._messages

    @property
    def outputCard(self) -> OutputCard:
        return self._output

    @property
    def sessionCard(self) -> SessionInfoCard:
        return self._session

    @property
    def actionBar(self) -> ActionBar:
        return self._actions

    @property
    def preferences(self) -> Preferences:
        return self._preferences

    def rowFor(self, role: InputRole):
        return self._inputs.rowFor(role)
