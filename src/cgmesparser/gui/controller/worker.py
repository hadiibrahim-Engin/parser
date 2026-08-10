"""The object that runs a conversion on a background thread.

The worker is the only place that calls into the backend. It translates one
``convert`` call into signals, and guarantees that ``finished`` is emitted no
matter how the call ended - a thread that never finishes is a window that never
closes.
"""

from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, Signal, Slot

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.result import ConversionOutcome, LogRecord, StageUpdate
from cgmesparser.gui.core.states import MessageLevel, ProcessingStage, StageState
from cgmesparser.gui.services.protocol import (
    CancellationToken,
    ConversionCancelled,
    ConversionService,
)


class ConversionWorker(QObject):
    """Runs one conversion and reports it as Qt signals.

    Every payload is a frozen dataclass, because these signals cross a thread
    boundary as queued connections and the receiving thread must not be handed
    something the worker can still change.
    """

    progressChanged = Signal(int)
    statusChanged = Signal(str)
    stageChanged = Signal(object)  # StageUpdate
    messageLogged = Signal(object)  # LogRecord
    completed = Signal(object)  # ConversionOutcome
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(
        self,
        service: ConversionService,
        request: ConversionRequest,
        token: CancellationToken,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._request = request
        self._token = token

    @Slot()
    def run(self) -> None:
        """Execute the conversion. Never raises into the thread."""
        try:
            outcome = self._service.convert(self._request, _SignalSink(self), self._token)
        except ConversionCancelled:
            self.cancelled.emit()
        except NotImplementedError as exc:
            # The expected outcome until the backend is integrated. Reported as
            # a plain failure rather than a crash, with no traceback noise.
            self.failed.emit(str(exc) or "Conversion is not implemented.")
        except Exception as exc:  # noqa: BLE001 - the thread boundary must not leak
            # Catching broadly here is deliberate and happens exactly once in
            # the codebase: an exception escaping a QThread terminates the
            # process. It is logged in full and surfaced, never swallowed.
            self.messageLogged.emit(LogRecord.now(MessageLevel.ERROR, traceback.format_exc().rstrip()))
            self.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self._emitOutcome(outcome)
        finally:
            self.finished.emit()

    def _emitOutcome(self, outcome: object) -> None:
        if isinstance(outcome, ConversionOutcome):
            self.completed.emit(outcome)
            return
        # A backend that returns the wrong type is a bug in the backend, not a
        # successful run; saying so beats rendering a broken summary card.
        self.failed.emit(
            f"The conversion service returned {type(outcome).__name__}, expected ConversionOutcome."
        )


class _SignalSink:
    """Adapts the backend's :class:`ProgressSink` calls onto worker signals.

    Its existence is what lets the backend stay free of Qt.
    """

    def __init__(self, worker: ConversionWorker) -> None:
        self._worker = worker

    def stage(self, stage: ProcessingStage, state: StageState) -> None:
        self._worker.stageChanged.emit(StageUpdate(stage=stage, state=state))

    def progress(self, percentage: int) -> None:
        self._worker.progressChanged.emit(max(0, min(100, int(percentage))))

    def status(self, text: str) -> None:
        self._worker.statusChanged.emit(str(text))

    def log(self, level: MessageLevel, message: str) -> None:
        self._worker.messageLogged.emit(LogRecord.now(level, str(message)))
