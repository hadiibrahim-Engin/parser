"""The contract a conversion backend must satisfy.

Deliberately free of Qt. A backend implementation reports progress by calling
methods on a :class:`ProgressSink`, and never knows that the other side of that
sink is a set of Qt signals.
"""

from __future__ import annotations

import threading
from typing import Protocol, runtime_checkable

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.result import ConversionOutcome
from cgmesparser.gui.core.states import MessageLevel, ProcessingStage, StageState


class ConversionCancelled(Exception):
    """Raised by a backend that noticed the run was cancelled and stopped."""


class CancellationToken:
    """A thread-safe "please stop" flag.

    Cancellation is cooperative. The token is set from the interface thread and
    polled by the backend between units of work; nothing is ever forcibly
    terminated, because killing a thread mid-write is how half-written files
    happen.
    """

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def isCancelled(self) -> bool:
        return self._event.is_set()

    def raiseIfCancelled(self) -> None:
        """Abort the current backend call if cancellation has been requested."""
        if self._event.is_set():
            raise ConversionCancelled()

    def wait(self, timeout: float) -> bool:
        """Sleep for ``timeout`` seconds, returning early if cancelled.

        Returns True when cancellation happened during the wait.
        """
        return self._event.wait(timeout)


@runtime_checkable
class ProgressSink(Protocol):
    """How a backend reports what it is doing."""

    def stage(self, stage: ProcessingStage, state: StageState) -> None:
        """Move one stepper node into a new state."""

    def progress(self, percentage: int) -> None:
        """Report overall completion, 0 to 100."""

    def status(self, text: str) -> None:
        """Set the one-line status shown beneath the progress bar."""

    def log(self, level: MessageLevel, message: str) -> None:
        """Append one line to the message log."""


@runtime_checkable
class ConversionService(Protocol):
    """The single entry point into the conversion backend."""

    def convert(
        self,
        request: ConversionRequest,
        sink: ProgressSink,
        token: CancellationToken,
    ) -> ConversionOutcome:
        """Run one conversion to completion.

        Implementations must poll ``token`` between units of work and raise
        :class:`ConversionCancelled` when it is set. Returning normally means
        the conversion succeeded and the outcome describes real output.
        """
        ...
