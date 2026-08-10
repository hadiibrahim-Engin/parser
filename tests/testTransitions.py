"""The state machine and the button-enablement matrix."""

from __future__ import annotations

import pytest

from cgmesparser.gui.core.states import ApplicationState
from cgmesparser.gui.core.transitions import (
    InvalidTransitionError,
    Trigger,
    buttonStatesFor,
    canApply,
    nextState,
)

IDLE = ApplicationState.IDLE
VALIDATING = ApplicationState.VALIDATING
READY = ApplicationState.READY
RUNNING = ApplicationState.RUNNING
STOPPING = ApplicationState.STOPPING
SUCCEEDED = ApplicationState.SUCCEEDED
FAILED = ApplicationState.FAILED


class TestTransitions:
    @pytest.mark.parametrize("start", [IDLE, READY, SUCCEEDED, FAILED])
    def testValidationCanBeRequestedFromAnySettledState(self, start: ApplicationState) -> None:
        assert nextState(start, Trigger.VALIDATE_REQUESTED) is VALIDATING

    def testPassingValidationReachesReady(self) -> None:
        assert nextState(VALIDATING, Trigger.VALIDATION_PASSED) is READY

    def testFailingValidationReturnsToIdle(self) -> None:
        assert nextState(VALIDATING, Trigger.VALIDATION_FAILED) is IDLE

    def testStartingFromReadyRuns(self) -> None:
        assert nextState(READY, Trigger.START_REQUESTED) is RUNNING

    @pytest.mark.parametrize("start", [SUCCEEDED, FAILED])
    def testAFinishedRunCanBeStartedAgain(self, start: ApplicationState) -> None:
        assert nextState(start, Trigger.START_REQUESTED) is RUNNING

    def testStoppingIsAStateOfItsOwn(self) -> None:
        assert nextState(RUNNING, Trigger.STOP_REQUESTED) is STOPPING

    def testCancellationReturnsToIdle(self) -> None:
        assert nextState(STOPPING, Trigger.CONVERSION_CANCELLED) is IDLE
        assert nextState(RUNNING, Trigger.CONVERSION_CANCELLED) is IDLE

    def testARunThatFinishesWhileStoppingStillReportsItsRealOutcome(self) -> None:
        assert nextState(STOPPING, Trigger.CONVERSION_SUCCEEDED) is SUCCEEDED
        assert nextState(STOPPING, Trigger.CONVERSION_FAILED) is FAILED

    @pytest.mark.parametrize("start", [IDLE, READY, VALIDATING, SUCCEEDED, FAILED])
    def testChangingAPathInvalidatesAPreviousValidation(self, start: ApplicationState) -> None:
        # READY must only ever mean "these exact paths were validated".
        assert nextState(start, Trigger.PATH_CHANGED) is IDLE

    @pytest.mark.parametrize("start", [RUNNING, STOPPING])
    def testPathChangesAreAbsorbedWhileARunOwnsTheInputs(self, start: ApplicationState) -> None:
        assert nextState(start, Trigger.PATH_CHANGED) is start

    def testStartingWhileRunningIsRejected(self) -> None:
        with pytest.raises(InvalidTransitionError):
            nextState(RUNNING, Trigger.START_REQUESTED)

    def testStoppingWhenNothingRunsIsRejected(self) -> None:
        with pytest.raises(InvalidTransitionError):
            nextState(IDLE, Trigger.STOP_REQUESTED)

    def testValidatingWhileRunningIsRejected(self) -> None:
        with pytest.raises(InvalidTransitionError):
            nextState(RUNNING, Trigger.VALIDATE_REQUESTED)

    def testTheErrorNamesBothSides(self) -> None:
        with pytest.raises(InvalidTransitionError) as raised:
            nextState(IDLE, Trigger.STOP_REQUESTED)
        assert raised.value.state is IDLE
        assert raised.value.trigger is Trigger.STOP_REQUESTED

    def testCanApplyAgreesWithNextState(self) -> None:
        for state in ApplicationState:
            for trigger in Trigger:
                if canApply(state, trigger):
                    nextState(state, trigger)  # must not raise
                else:
                    with pytest.raises(InvalidTransitionError):
                        nextState(state, trigger)


class TestButtonStates:
    def testValidateNeedsEveryPath(self) -> None:
        assert buttonStatesFor(IDLE, hasAllPaths=False, outputDirectoryExists=False).validate is False
        assert buttonStatesFor(IDLE, hasAllPaths=True, outputDirectoryExists=False).validate is True

    def testStartIsOnlyAvailableOnceValidated(self) -> None:
        assert buttonStatesFor(IDLE, True, True).start is False
        assert buttonStatesFor(READY, True, True).start is True

    def testAFinishedRunCanBeRepeatedWithoutRevalidating(self) -> None:
        assert buttonStatesFor(SUCCEEDED, True, True).start is True
        assert buttonStatesFor(FAILED, True, True).start is True

    def testStopIsOnlyAvailableWhileRunning(self) -> None:
        assert buttonStatesFor(RUNNING, True, True).stop is True
        assert buttonStatesFor(STOPPING, True, True).stop is False
        assert buttonStatesFor(READY, True, True).stop is False

    def testExitIsBlockedWhileARunOwnsTheThread(self) -> None:
        assert buttonStatesFor(RUNNING, True, True).exit is False
        assert buttonStatesFor(STOPPING, True, True).exit is False
        assert buttonStatesFor(VALIDATING, True, True).exit is True

    def testPreferencesAreAlwaysReachable(self) -> None:
        assert all(buttonStatesFor(state, False, False).preferences for state in ApplicationState)

    def testOpenOutputFolderFollowsTheDirectoryNotTheState(self) -> None:
        for state in ApplicationState:
            assert buttonStatesFor(state, True, True).openOutputFolder is True
            assert buttonStatesFor(state, True, False).openOutputFolder is False

    def testInputsAreLockedWhileBusy(self) -> None:
        assert buttonStatesFor(RUNNING, True, True).inputsEditable is False
        assert buttonStatesFor(STOPPING, True, True).inputsEditable is False
        assert buttonStatesFor(VALIDATING, True, True).inputsEditable is False
        assert buttonStatesFor(IDLE, True, True).inputsEditable is True

    def testNothingIsStartableWhileValidating(self) -> None:
        states = buttonStatesFor(VALIDATING, True, True)
        assert (states.validate, states.start, states.stop) == (False, False, False)
