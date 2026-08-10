"""The enumerations the whole application agrees on.

Every value that a widget renders, a controller decides on, or a test asserts
against is named here exactly once. Display strings live on the enum members so
there is no second table of labels to keep in step.
"""

from __future__ import annotations

from enum import Enum, unique


@unique
class ApplicationState(Enum):
    """Where the application is in the validate / convert lifecycle."""

    IDLE = "idle"
    VALIDATING = "validating"
    READY = "ready"
    RUNNING = "running"
    STOPPING = "stopping"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    @property
    def isBusy(self) -> bool:
        """Whether a background operation owns the application right now."""
        return self in (ApplicationState.VALIDATING, ApplicationState.RUNNING, ApplicationState.STOPPING)


@unique
class ProcessingStage(Enum):
    """The six stages shown in the stepper.

    These are user-interface definitions only. Nothing here claims to describe
    what the conversion backend actually does; the mapping from backend work to
    these stages is defined when that backend is integrated.
    """

    LOAD_MODELS = "Load Models"
    VALIDATE_INPUTS = "Validate Inputs"
    EXTRACT_LINES = "Extract Lines"
    CLASSIFY_SUBSTATIONS = "Classify Substations"
    MERGE_DATA = "Merge Data"
    EXCEL_EXPORT = "Excel Export"

    @property
    def label(self) -> str:
        return self.value

    @property
    def position(self) -> int:
        """Zero-based index of this stage in display order."""
        return ORDERED_STAGES.index(self)


ORDERED_STAGES: tuple[ProcessingStage, ...] = tuple(ProcessingStage)


@unique
class StageState(Enum):
    """How one stepper node is drawn."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@unique
class MessageLevel(Enum):
    """Severity of one line in the message log."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@unique
class InputRole(Enum):
    """One of the four things the user selects, labelled as the UI shows it."""

    PROFILE_ZIP = "CGMES Profile ZIP"
    SNAPSHOT_DATASET = "Snapshot CGMES Dataset"
    CIM_CACHE_DATASET = "CIM Cache Dataset"
    OUTPUT_DIRECTORY = "Output Directory"

    @property
    def label(self) -> str:
        return self.value


ORDERED_ROLES: tuple[InputRole, ...] = tuple(InputRole)


@unique
class CheckStatus(Enum):
    """Outcome of one input check.

    Only :attr:`ERROR` blocks a conversion. A warning is information the user
    should see but is free to proceed past.
    """

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
