"""The backend seam: cancellation token, the default service, the demo service."""

from __future__ import annotations

import threading

import pytest

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.result import ConversionOutcome
from cgmesparser.gui.core.states import ORDERED_STAGES, MessageLevel, ProcessingStage, StageState
from cgmesparser.gui.services.demo import DEMO_BANNER, DemoConversionService
from cgmesparser.gui.services.protocol import (
    CancellationToken,
    ConversionCancelled,
    ConversionService,
    ProgressSink,
)
from cgmesparser.gui.services.unimplemented import NOT_IMPLEMENTED_MESSAGE, UnimplementedConversionService


class RecordingSink:
    """Captures everything a service reports."""

    def __init__(self) -> None:
        self.stages: list[tuple[ProcessingStage, StageState]] = []
        self.percentages: list[int] = []
        self.statuses: list[str] = []
        self.messages: list[tuple[MessageLevel, str]] = []

    def stage(self, stage: ProcessingStage, state: StageState) -> None:
        self.stages.append((stage, state))

    def progress(self, percentage: int) -> None:
        self.percentages.append(percentage)

    def status(self, text: str) -> None:
        self.statuses.append(text)

    def log(self, level: MessageLevel, message: str) -> None:
        self.messages.append((level, message))


class TestCancellationToken:
    def testStartsUncancelled(self) -> None:
        assert CancellationToken().isCancelled is False

    def testCancelIsVisibleAndRaises(self) -> None:
        token = CancellationToken()
        token.cancel()
        assert token.isCancelled is True
        with pytest.raises(ConversionCancelled):
            token.raiseIfCancelled()

    def testRaiseIsSilentUntilCancelled(self) -> None:
        CancellationToken().raiseIfCancelled()

    def testWaitReturnsEarlyWhenCancelledFromAnotherThread(self) -> None:
        token = CancellationToken()
        threading.Timer(0.05, token.cancel).start()
        assert token.wait(5.0) is True

    def testWaitTimesOutWhenNothingCancels(self) -> None:
        assert CancellationToken().wait(0.01) is False


class TestUnimplementedService:
    def testItSatisfiesTheProtocol(self) -> None:
        assert isinstance(UnimplementedConversionService(), ConversionService)

    def testItRefusesToPretend(self) -> None:
        with pytest.raises(NotImplementedError) as raised:
            UnimplementedConversionService().convert(
                ConversionRequest(), RecordingSink(), CancellationToken()
            )
        assert str(raised.value) == NOT_IMPLEMENTED_MESSAGE

    def testItReportsNothingBeforeFailing(self) -> None:
        sink = RecordingSink()
        with pytest.raises(NotImplementedError):
            UnimplementedConversionService().convert(ConversionRequest(), sink, CancellationToken())
        assert sink.stages == []
        assert sink.percentages == []


class TestDemoService:
    def testItWalksEveryStage(self, tmp_path) -> None:
        sink = RecordingSink()
        service = DemoConversionService(secondsPerStage=0.0)
        outcome = service.convert(
            ConversionRequest(outputDirectory=tmp_path), sink, CancellationToken()
        )

        activated = [stage for stage, state in sink.stages if state is StageState.ACTIVE]
        completed = [stage for stage, state in sink.stages if state is StageState.COMPLETED]
        assert activated == list(ORDERED_STAGES)
        assert completed == list(ORDERED_STAGES)
        assert sink.percentages[-1] == 100
        assert isinstance(outcome, ConversionOutcome)

    def testItAnnouncesItselfBeforeDoingAnything(self, tmp_path) -> None:
        sink = RecordingSink()
        DemoConversionService(secondsPerStage=0.0).convert(
            ConversionRequest(outputDirectory=tmp_path), sink, CancellationToken()
        )
        assert sink.messages[0] == (MessageLevel.WARNING, DEMO_BANNER)

    def testItReportsZeroSoItCannotPassForARealRun(self, tmp_path) -> None:
        outcome = DemoConversionService(secondsPerStage=0.0).convert(
            ConversionRequest(outputDirectory=tmp_path), RecordingSink(), CancellationToken()
        )
        assert (outcome.excelFileCount, outcome.detectedLines, outcome.detectedSubstations) == (0, 0, 0)

    def testItWritesNothing(self, tmp_path) -> None:
        DemoConversionService(secondsPerStage=0.0).convert(
            ConversionRequest(outputDirectory=tmp_path), RecordingSink(), CancellationToken()
        )
        assert list(tmp_path.iterdir()) == []

    def testItHonoursCancellationImmediately(self, tmp_path) -> None:
        token = CancellationToken()
        token.cancel()
        with pytest.raises(ConversionCancelled):
            DemoConversionService(secondsPerStage=0.0).convert(
                ConversionRequest(outputDirectory=tmp_path), RecordingSink(), token
            )


class TestProtocolShape:
    def testARecordingSinkSatisfiesProgressSink(self) -> None:
        assert isinstance(RecordingSink(), ProgressSink)
