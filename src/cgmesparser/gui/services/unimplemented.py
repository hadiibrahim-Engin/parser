"""The service the application ships with today.

Pressing Start drives the real worker thread, the real state transitions and the
real error path, and lands in FAILED carrying this message. That is intentional:
the whole mechanism is exercised, and at no point does the interface suggest a
conversion happened.
"""

from __future__ import annotations

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.result import ConversionOutcome
from cgmesparser.gui.services.protocol import CancellationToken, ProgressSink

NOT_IMPLEMENTED_MESSAGE = "CGMES/CIMLA backend integration has not been implemented yet."


class UnimplementedConversionService:
    """A :class:`~cgmesparser.gui.services.protocol.ConversionService` that refuses to pretend."""

    def convert(
        self,
        request: ConversionRequest,
        sink: ProgressSink,
        token: CancellationToken,
    ) -> ConversionOutcome:
        raise NotImplementedError(NOT_IMPLEMENTED_MESSAGE)
