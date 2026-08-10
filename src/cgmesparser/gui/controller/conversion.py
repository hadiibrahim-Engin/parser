"""The application controller.

Owns the request, the application state, the worker thread and the cancellation
token. Decides nothing about pixels and imports no widget: the main window
subscribes to these signals and renders the result.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from cgmesparser.gui.controller.worker import ConversionWorker
from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.result import ConversionOutcome, LogRecord
from cgmesparser.gui.core.states import ApplicationState, InputRole, MessageLevel
from cgmesparser.gui.core.transitions import (
    ButtonStates,
    InvalidTransitionError,
    Trigger,
    buttonStatesFor,
    nextState,
)
from cgmesparser.gui.core.validation import ExtraChecker, ValidationReport, validateRequest
from cgmesparser.gui.services.protocol import CancellationToken, ConversionService

_THREAD_STOP_TIMEOUT_MS = 5000


class ConversionController(QObject):
    """Drives one application session."""

    stateChanged = Signal(object)  # ApplicationState
    requestChanged = Signal(object)  # ConversionRequest
    validationCompleted = Signal(object)  # ValidationReport
    validationCleared = Signal()
    stageChanged = Signal(object)  # StageUpdate
    progressChanged = Signal(int)
    statusChanged = Signal(str)
    messageLogged = Signal(object)  # LogRecord
    outcomeReady = Signal(object)  # ConversionOutcome
    buttonStatesChanged = Signal(object)  # ButtonStates
    runStarted = Signal()

    def __init__(
        self,
        service: ConversionService,
        request: ConversionRequest | None = None,
        extraCheckers: tuple[ExtraChecker, ...] = (),
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._request = request if request is not None else ConversionRequest()
        self._extraCheckers = extraCheckers
        self._state = ApplicationState.IDLE
        self._report: ValidationReport | None = None

        self._thread: QThread | None = None
        self._worker: ConversionWorker | None = None
        self._token: CancellationToken | None = None

    # -- observable state -----------------------------------------------------

    @property
    def state(self) -> ApplicationState:
        return self._state

    @property
    def request(self) -> ConversionRequest:
        return self._request

    @property
    def report(self) -> ValidationReport | None:
        return self._report

    def buttonStates(self) -> ButtonStates:
        return buttonStatesFor(
            self._state,
            hasAllPaths=self._request.isComplete,
            outputDirectoryExists=self._outputDirectoryUsable(),
        )

    def emitCurrentState(self) -> None:
        """Push the current state out to freshly connected listeners."""
        self.stateChanged.emit(self._state)
        self.requestChanged.emit(self._request)
        self._publishButtonStates()

    # -- input ----------------------------------------------------------------

    def setPath(self, role: InputRole, path: Path | None) -> None:
        """Record a new selection and invalidate any previous validation."""
        if self._state.isBusy and self._state is not ApplicationState.VALIDATING:
            self.log(MessageLevel.WARNING, "Inputs cannot be changed while a conversion is running.")
            return
        if self._request.pathFor(role) == path:
            return

        self._request = self._request.withPath(role, path)
        self.requestChanged.emit(self._request)
        self.log(
            MessageLevel.INFO,
            f"{role.label} {'cleared' if path is None else f'selected: {path}'}",
        )

        if self._report is not None:
            self._report = None
            self.validationCleared.emit()
        self._applyTrigger(Trigger.PATH_CHANGED)

    def setRequest(self, request: ConversionRequest) -> None:
        """Replace the whole request, as when restoring saved settings."""
        self._request = request
        self.requestChanged.emit(self._request)
        self._publishButtonStates()

    # -- actions --------------------------------------------------------------

    def validateInputs(self) -> None:
        """Run the filesystem checks and publish the report.

        Domain-specific validation is added by passing ``extraCheckers`` to the
        constructor; this method does not change when that happens.
        """
        if not self._applyTrigger(Trigger.VALIDATE_REQUESTED):
            return
        self.log(MessageLevel.INFO, "Validating input paths and dataset availability...")

        report = validateRequest(self._request, self._extraCheckers)
        self._report = report
        self.validationCompleted.emit(report)

        for check in report.checks:
            level = _LEVEL_FOR_STATUS[check.status.value]
            if level is not None:
                self.log(level, f"{check.role.label}: {check.message}")

        if report.isValid:
            self.log(MessageLevel.INFO, "All required inputs are valid.")
            self._applyTrigger(Trigger.VALIDATION_PASSED)
        else:
            self.log(MessageLevel.ERROR, report.summary)
            self._applyTrigger(Trigger.VALIDATION_FAILED)

    def startConversion(self) -> None:
        """Hand the request to the conversion service on a background thread."""
        if self._thread is not None:
            self.log(MessageLevel.WARNING, "A conversion is already running.")
            return
        if not self._applyTrigger(Trigger.START_REQUESTED):
            return

        self.log(MessageLevel.INFO, "Start conversion requested.")
        self.runStarted.emit()

        self._token = CancellationToken()
        self._thread = QThread(self)
        self._worker = ConversionWorker(self._service, self._request, self._token)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progressChanged.connect(self.progressChanged)
        self._worker.statusChanged.connect(self.statusChanged)
        self._worker.stageChanged.connect(self.stageChanged)
        self._worker.messageLogged.connect(self.messageLogged)
        self._worker.completed.connect(self._onCompleted)
        self._worker.failed.connect(self._onFailed)
        self._worker.cancelled.connect(self._onCancelled)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._disposeThread)

        self._thread.start()

    def stopConversion(self) -> None:
        """Ask the running conversion to stop at its next checkpoint.

        Cancellation is cooperative by design. Nothing is forcibly terminated,
        because killing a thread mid-write is how half-written files happen.
        """
        if self._token is None or self._state is not ApplicationState.RUNNING:
            return
        if not self._applyTrigger(Trigger.STOP_REQUESTED):
            return
        self.log(MessageLevel.WARNING, "Stop requested. Waiting for the current stage to finish...")
        self.statusChanged.emit("Stopping...")
        self._token.cancel()

    def openOutputFolder(self) -> None:
        """Reveal the configured output directory in the system file manager."""
        directory = self._request.outputDirectory
        if directory is None:
            self.log(MessageLevel.WARNING, "No output directory is selected.")
            return
        if not directory.is_dir():
            self.log(MessageLevel.WARNING, f"Output directory does not exist: {directory}")
            return
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory))):
            self.log(MessageLevel.INFO, f"Opened output directory: {directory}")
        else:
            self.log(MessageLevel.ERROR, f"Could not open output directory: {directory}")

    def shutdown(self) -> None:
        """Cancel any run and wait for the thread, with a bounded timeout."""
        if self._token is not None:
            self._token.cancel()
        thread = self._thread
        if thread is not None and thread.isRunning():
            thread.quit()
            if not thread.wait(_THREAD_STOP_TIMEOUT_MS):
                # Reported rather than escalated: terminating the thread here
                # could corrupt whatever the backend was writing.
                self.log(
                    MessageLevel.ERROR,
                    "The conversion thread did not stop within 5 seconds.",
                )

    # -- logging --------------------------------------------------------------

    def log(self, level: MessageLevel, message: str) -> None:
        """Emit one interface-level log line."""
        self.messageLogged.emit(LogRecord.now(level, message))

    # -- worker callbacks -----------------------------------------------------

    def _onCompleted(self, outcome: ConversionOutcome) -> None:
        self._applyTrigger(Trigger.CONVERSION_SUCCEEDED)
        self.outcomeReady.emit(outcome)
        self.log(MessageLevel.INFO, "Conversion completed.")
        self.statusChanged.emit("Conversion completed")
        self.progressChanged.emit(100)

    def _onFailed(self, message: str) -> None:
        self._applyTrigger(Trigger.CONVERSION_FAILED)
        self.log(MessageLevel.ERROR, message)
        self.statusChanged.emit("Conversion failed")

    def _onCancelled(self) -> None:
        self._applyTrigger(Trigger.CONVERSION_CANCELLED)
        self.log(MessageLevel.WARNING, "Conversion cancelled.")
        self.statusChanged.emit("Cancelled")
        self.progressChanged.emit(0)

    def _disposeThread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self._token = None

    # -- internals ------------------------------------------------------------

    def _applyTrigger(self, trigger: Trigger) -> bool:
        """Move to the next state, reporting whether the trigger was accepted."""
        try:
            updated = nextState(self._state, trigger)
        except InvalidTransitionError:
            return False
        if updated is not self._state:
            self._state = updated
            self.stateChanged.emit(updated)
        self._publishButtonStates()
        return True

    def _publishButtonStates(self) -> None:
        self.buttonStatesChanged.emit(self.buttonStates())

    def _outputDirectoryUsable(self) -> bool:
        directory = self._request.outputDirectory
        return directory is not None and directory.is_dir()


_LEVEL_FOR_STATUS: dict[str, MessageLevel | None] = {
    "ok": None,
    "warning": MessageLevel.WARNING,
    "error": MessageLevel.ERROR,
}
