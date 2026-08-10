"""Controller behaviour, including the real worker thread."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from cgmesparser.gui.controller.conversion import ConversionController
from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.result import ConversionOutcome
from cgmesparser.gui.core.states import ApplicationState, InputRole, MessageLevel, ProcessingStage, StageState
from cgmesparser.gui.services.protocol import CancellationToken, ConversionCancelled, ProgressSink
from cgmesparser.gui.services.unimplemented import NOT_IMPLEMENTED_MESSAGE, UnimplementedConversionService

TIMEOUT = 5000


class SucceedingService:
    """Reports one stage, then returns a real outcome."""

    def __init__(self, outputDirectory: Path) -> None:
        self._outputDirectory = outputDirectory

    def convert(self, request, sink: ProgressSink, token: CancellationToken) -> ConversionOutcome:
        sink.stage(ProcessingStage.LOAD_MODELS, StageState.ACTIVE)
        sink.status("Loading")
        sink.progress(50)
        sink.log(MessageLevel.INFO, "backend running")
        sink.stage(ProcessingStage.LOAD_MODELS, StageState.COMPLETED)
        return ConversionOutcome(self._outputDirectory, 2, 10, 4, datetime.now())


class ExplodingService:
    def convert(self, request, sink, token):
        raise ValueError("the backend fell over")


class CancellableService:
    """Waits for the token, the way a real backend polls between stages."""

    def convert(self, request, sink, token: CancellationToken):
        token.wait(5.0)
        token.raiseIfCancelled()
        raise AssertionError("cancellation was never requested")


class WrongTypeService:
    def convert(self, request, sink, token):
        return {"excelFiles": 3}


def controllerFor(service, request: ConversionRequest | None = None) -> ConversionController:
    return ConversionController(service, request)


class TestPathHandling:
    def testSettingAPathAnnouncesTheNewRequest(self, qtbot, tmp_path: Path) -> None:
        controller = controllerFor(UnimplementedConversionService())
        with qtbot.waitSignal(controller.requestChanged, timeout=TIMEOUT) as caught:
            controller.setPath(InputRole.PROFILE_ZIP, tmp_path / "a.zip")
        assert caught.args[0].profileZip == tmp_path / "a.zip"

    def testSettingTheSamePathAgainIsIgnored(self, qtbot, tmp_path: Path) -> None:
        controller = controllerFor(UnimplementedConversionService())
        controller.setPath(InputRole.PROFILE_ZIP, tmp_path / "a.zip")
        with qtbot.assertNotEmitted(controller.requestChanged):
            controller.setPath(InputRole.PROFILE_ZIP, tmp_path / "a.zip")

    def testChangingAPathInvalidatesAPreviousValidation(self, qtbot, validRequest) -> None:
        controller = controllerFor(UnimplementedConversionService(), validRequest)
        controller.validateInputs()
        assert controller.state is ApplicationState.READY

        with qtbot.waitSignal(controller.validationCleared, timeout=TIMEOUT):
            controller.setPath(InputRole.PROFILE_ZIP, None)
        assert controller.state is ApplicationState.IDLE
        assert controller.report is None


class TestValidation:
    def testAValidRequestReachesReady(self, qtbot, validRequest) -> None:
        controller = controllerFor(UnimplementedConversionService(), validRequest)
        with qtbot.waitSignal(controller.validationCompleted, timeout=TIMEOUT) as caught:
            controller.validateInputs()
        assert caught.args[0].isValid is True
        assert controller.state is ApplicationState.READY

    def testAnInvalidRequestStaysIdle(self, qtbot) -> None:
        controller = controllerFor(UnimplementedConversionService())
        controller.validateInputs()
        assert controller.state is ApplicationState.IDLE

    def testWarningsAreLoggedButDoNotBlock(self, qtbot, validRequest) -> None:
        controller = controllerFor(UnimplementedConversionService(), validRequest)
        logged: list[str] = []
        controller.messageLogged.connect(lambda record: logged.append(record.message))
        controller.validateInputs()
        assert any("Directory exists" in message for message in logged)
        assert controller.state is ApplicationState.READY

    def testDomainCheckersAreConsulted(self, qtbot, validRequest) -> None:
        from cgmesparser.gui.core.states import CheckStatus
        from cgmesparser.gui.core.validation import InputCheck

        def refuse(request):
            yield InputCheck(InputRole.SNAPSHOT_DATASET, CheckStatus.ERROR, "No SSH profile")

        controller = ConversionController(UnimplementedConversionService(), validRequest, (refuse,))
        controller.validateInputs()
        assert controller.state is ApplicationState.IDLE


class TestConversionRun:
    def testASucceedingRunReportsItsOutcome(self, qtbot, validRequest, tmp_path: Path) -> None:
        controller = controllerFor(SucceedingService(tmp_path), validRequest)
        controller.validateInputs()

        with qtbot.waitSignal(controller.outcomeReady, timeout=TIMEOUT) as caught:
            controller.startConversion()

        assert controller.state is ApplicationState.SUCCEEDED
        assert caught.args[0].excelFileCount == 2
        qtbot.waitUntil(lambda: controller._thread is None, timeout=TIMEOUT)

    def testTheDefaultServiceFailsWithItsMessage(self, qtbot, validRequest) -> None:
        controller = controllerFor(UnimplementedConversionService(), validRequest)
        controller.validateInputs()

        errors: list[str] = []
        controller.messageLogged.connect(
            lambda record: errors.append(record.message) if record.level is MessageLevel.ERROR else None
        )
        with qtbot.waitSignal(controller.stateChanged, timeout=TIMEOUT):
            controller.startConversion()
        qtbot.waitUntil(lambda: controller.state is ApplicationState.FAILED, timeout=TIMEOUT)
        assert NOT_IMPLEMENTED_MESSAGE in errors

    def testAnUnexpectedExceptionBecomesAFailureNotACrash(self, qtbot, validRequest) -> None:
        controller = controllerFor(ExplodingService(), validRequest)
        controller.validateInputs()
        controller.startConversion()
        qtbot.waitUntil(lambda: controller.state is ApplicationState.FAILED, timeout=TIMEOUT)

    def testABackendReturningTheWrongTypeIsNotTreatedAsSuccess(self, qtbot, validRequest) -> None:
        controller = controllerFor(WrongTypeService(), validRequest)
        controller.validateInputs()
        controller.startConversion()
        qtbot.waitUntil(lambda: controller.state is ApplicationState.FAILED, timeout=TIMEOUT)

    def testStoppingReachesStoppingThenIdle(self, qtbot, validRequest) -> None:
        controller = controllerFor(CancellableService(), validRequest)
        controller.validateInputs()
        controller.startConversion()
        qtbot.waitUntil(lambda: controller.state is ApplicationState.RUNNING, timeout=TIMEOUT)

        controller.stopConversion()
        assert controller.state is ApplicationState.STOPPING

        qtbot.waitUntil(lambda: controller.state is ApplicationState.IDLE, timeout=TIMEOUT)
        qtbot.waitUntil(lambda: controller._thread is None, timeout=TIMEOUT)

    def testStoppingWhenNothingRunsIsHarmless(self, qtbot, validRequest) -> None:
        controller = controllerFor(UnimplementedConversionService(), validRequest)
        controller.stopConversion()
        assert controller.state is ApplicationState.IDLE

    def testASecondStartIsRefusedWhileOneRuns(self, qtbot, validRequest) -> None:
        controller = controllerFor(CancellableService(), validRequest)
        controller.validateInputs()
        controller.startConversion()
        qtbot.waitUntil(lambda: controller.state is ApplicationState.RUNNING, timeout=TIMEOUT)

        controller.startConversion()  # must not spawn a second thread
        assert controller.state is ApplicationState.RUNNING

        controller.stopConversion()
        qtbot.waitUntil(lambda: controller.state is ApplicationState.IDLE, timeout=TIMEOUT)

    def testPathsCannotChangeMidRun(self, qtbot, validRequest, tmp_path: Path) -> None:
        controller = controllerFor(CancellableService(), validRequest)
        controller.validateInputs()
        controller.startConversion()
        qtbot.waitUntil(lambda: controller.state is ApplicationState.RUNNING, timeout=TIMEOUT)

        controller.setPath(InputRole.PROFILE_ZIP, tmp_path / "other.zip")
        assert controller.request.profileZip == validRequest.profileZip

        controller.stopConversion()
        qtbot.waitUntil(lambda: controller.state is ApplicationState.IDLE, timeout=TIMEOUT)

    def testShutdownCancelsAndJoins(self, qtbot, validRequest) -> None:
        controller = controllerFor(CancellableService(), validRequest)
        controller.validateInputs()
        controller.startConversion()
        qtbot.waitUntil(lambda: controller.state is ApplicationState.RUNNING, timeout=TIMEOUT)

        controller.shutdown()
        qtbot.waitUntil(lambda: controller._thread is None, timeout=TIMEOUT)


class TestButtonStatePublication:
    def testStatesArePublishedOnEveryChange(self, qtbot, validRequest) -> None:
        controller = controllerFor(UnimplementedConversionService(), validRequest)
        with qtbot.waitSignal(controller.buttonStatesChanged, timeout=TIMEOUT) as caught:
            controller.emitCurrentState()
        assert caught.args[0].validate is True
        assert caught.args[0].start is False

    def testStartUnlocksOnlyAfterValidation(self, qtbot, validRequest) -> None:
        controller = controllerFor(UnimplementedConversionService(), validRequest)
        assert controller.buttonStates().start is False
        controller.validateInputs()
        assert controller.buttonStates().start is True


class TestOpenOutputFolder:
    def testMissingDirectoryIsReportedNotOpened(self, qtbot, tmp_path: Path) -> None:
        controller = controllerFor(
            UnimplementedConversionService(),
            ConversionRequest(outputDirectory=tmp_path / "absent"),
        )
        warnings: list[str] = []
        controller.messageLogged.connect(
            lambda record: warnings.append(record.message)
            if record.level is MessageLevel.WARNING
            else None
        )
        controller.openOutputFolder()
        assert any("does not exist" in message for message in warnings)

    def testNoDirectorySelectedIsReported(self, qtbot) -> None:
        controller = controllerFor(UnimplementedConversionService())
        warnings: list[str] = []
        controller.messageLogged.connect(
            lambda record: warnings.append(record.message)
            if record.level is MessageLevel.WARNING
            else None
        )
        controller.openOutputFolder()
        assert warnings == ["No output directory is selected."]


@pytest.mark.parametrize("service", [UnimplementedConversionService(), SucceedingService(Path("."))])
def testEveryServiceCanBeCancelledBeforeItStarts(service) -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises((ConversionCancelled, NotImplementedError)):
        token.raiseIfCancelled()
        service.convert(ConversionRequest(), None, token)
