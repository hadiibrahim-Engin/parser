"""The application state machine and the button-enablement matrix.

Both are pure functions over enums. Keeping them here, rather than spread across
widgets as ad-hoc ``setEnabled`` calls, means the rules can be read in one place
and asserted exhaustively in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique

from cgmesparser.gui.core.states import ApplicationState


@unique
class Trigger(Enum):
    """Something that happened which may move the application to a new state."""

    PATH_CHANGED = "pathChanged"
    VALIDATE_REQUESTED = "validateRequested"
    VALIDATION_PASSED = "validationPassed"
    VALIDATION_FAILED = "validationFailed"
    START_REQUESTED = "startRequested"
    STOP_REQUESTED = "stopRequested"
    CONVERSION_SUCCEEDED = "conversionSucceeded"
    CONVERSION_FAILED = "conversionFailed"
    CONVERSION_CANCELLED = "conversionCancelled"


class InvalidTransitionError(RuntimeError):
    """Raised when a trigger arrives in a state that cannot handle it."""

    def __init__(self, state: ApplicationState, trigger: Trigger) -> None:
        super().__init__(f"Cannot apply {trigger.name} while in state {state.name}")
        self.state = state
        self.trigger = trigger


_IDLE_LIKE = (
    ApplicationState.IDLE,
    ApplicationState.READY,
    ApplicationState.SUCCEEDED,
    ApplicationState.FAILED,
)

_TRANSITIONS: dict[tuple[ApplicationState, Trigger], ApplicationState] = {
    **{(state, Trigger.VALIDATE_REQUESTED): ApplicationState.VALIDATING for state in _IDLE_LIKE},
    (ApplicationState.VALIDATING, Trigger.VALIDATION_PASSED): ApplicationState.READY,
    (ApplicationState.VALIDATING, Trigger.VALIDATION_FAILED): ApplicationState.IDLE,
    **{
        (state, Trigger.START_REQUESTED): ApplicationState.RUNNING
        for state in (ApplicationState.READY, ApplicationState.SUCCEEDED, ApplicationState.FAILED)
    },
    (ApplicationState.RUNNING, Trigger.STOP_REQUESTED): ApplicationState.STOPPING,
    (ApplicationState.RUNNING, Trigger.CONVERSION_SUCCEEDED): ApplicationState.SUCCEEDED,
    (ApplicationState.RUNNING, Trigger.CONVERSION_FAILED): ApplicationState.FAILED,
    (ApplicationState.RUNNING, Trigger.CONVERSION_CANCELLED): ApplicationState.IDLE,
    (ApplicationState.STOPPING, Trigger.CONVERSION_CANCELLED): ApplicationState.IDLE,
    # A run that finishes on its own while a stop is pending still reports its
    # real outcome; the stop simply arrived too late to matter.
    (ApplicationState.STOPPING, Trigger.CONVERSION_SUCCEEDED): ApplicationState.SUCCEEDED,
    (ApplicationState.STOPPING, Trigger.CONVERSION_FAILED): ApplicationState.FAILED,
    # Changing any path invalidates a previous validation, so READY is only ever
    # reached by validating the exact set of paths currently selected.
    **{
        (state, Trigger.PATH_CHANGED): ApplicationState.IDLE
        for state in (*_IDLE_LIKE, ApplicationState.VALIDATING)
    },
}

# While a conversion owns the inputs they cannot change, so the trigger is
# absorbed rather than rejected.
_ABSORBED: frozenset[tuple[ApplicationState, Trigger]] = frozenset(
    {
        (ApplicationState.RUNNING, Trigger.PATH_CHANGED),
        (ApplicationState.STOPPING, Trigger.PATH_CHANGED),
    }
)


def nextState(current: ApplicationState, trigger: Trigger) -> ApplicationState:
    """Apply ``trigger`` to ``current``.

    Raises :class:`InvalidTransitionError` for a combination the state machine
    does not define, rather than silently staying put.
    """
    if (current, trigger) in _ABSORBED:
        return current
    try:
        return _TRANSITIONS[(current, trigger)]
    except KeyError:
        raise InvalidTransitionError(current, trigger) from None


def canApply(current: ApplicationState, trigger: Trigger) -> bool:
    """Whether ``trigger`` is legal in ``current``, without raising."""
    return (current, trigger) in _ABSORBED or (current, trigger) in _TRANSITIONS


@dataclass(frozen=True, slots=True)
class ButtonStates:
    """Enabled state for every action the user can take."""

    preferences: bool
    validate: bool
    start: bool
    stop: bool
    exit: bool
    openOutputFolder: bool
    inputsEditable: bool


def buttonStatesFor(
    state: ApplicationState,
    hasAllPaths: bool,
    outputDirectoryExists: bool,
) -> ButtonStates:
    """Derive every button's enabled state.

    This is the only place that decides enablement. Widgets apply the result;
    they never reason about it themselves.
    """
    running = state in (ApplicationState.RUNNING, ApplicationState.STOPPING)
    settled = state in _IDLE_LIKE

    return ButtonStates(
        preferences=True,
        validate=settled and hasAllPaths,
        start=state in (ApplicationState.READY, ApplicationState.SUCCEEDED, ApplicationState.FAILED),
        stop=state is ApplicationState.RUNNING,
        exit=not running,
        openOutputFolder=outputDirectoryExists,
        inputsEditable=not running and state is not ApplicationState.VALIDATING,
    )
