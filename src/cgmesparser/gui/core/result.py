"""Values that travel from the conversion backend back to the interface.

These cross a thread boundary as queued-signal payloads, so they are frozen:
the receiving thread cannot observe a half-written object.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cgmesparser.gui.core.states import MessageLevel, ProcessingStage, StageState


@dataclass(frozen=True, slots=True)
class LogRecord:
    """One line in the message log."""

    timestamp: datetime
    level: MessageLevel
    message: str

    @classmethod
    def now(cls, level: MessageLevel, message: str) -> LogRecord:
        return cls(timestamp=datetime.now(), level=level, message=message)

    @property
    def clockTime(self) -> str:
        return self.timestamp.strftime("%H:%M:%S")


@dataclass(frozen=True, slots=True)
class StageUpdate:
    """A single stepper node changing state."""

    stage: ProcessingStage
    state: StageState


@dataclass(frozen=True, slots=True)
class ConversionOutcome:
    """What a finished conversion reports back.

    This is the contract the backend will fill in. Nothing in the current phase
    constructs one outside of tests and the opt-in demo service.
    """

    outputDirectory: Path
    excelFileCount: int
    detectedLines: int
    detectedSubstations: int
    finishedAt: datetime
