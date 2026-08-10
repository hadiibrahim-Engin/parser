"""A backend stand-in for working on the interface itself.

This exists so the stepper, progress bar, status line and message log can be
seen in motion without a real backend. It is reachable only through ``--demo``,
it writes nothing to disk, and every line it logs is prefixed so no screenshot
of it can be mistaken for a real run.

The outcome it returns reports zeros. Inventing plausible-looking counts would
make a demo run indistinguishable from a real one, which is exactly what this
module must never do.
"""

from __future__ import annotations

from datetime import datetime

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.result import ConversionOutcome
from cgmesparser.gui.core.states import ORDERED_STAGES, MessageLevel, StageState
from cgmesparser.gui.services.protocol import CancellationToken, ProgressSink

DEMO_BANNER = "DEMO MODE - no conversion is performed and no files are written"
_PREFIX = "[DEMO]"


class DemoConversionService:
    """Walks the six stages on a timer. Performs no work of any kind."""

    def __init__(self, secondsPerStage: float = 0.9) -> None:
        self._secondsPerStage = secondsPerStage

    def convert(
        self,
        request: ConversionRequest,
        sink: ProgressSink,
        token: CancellationToken,
    ) -> ConversionOutcome:
        sink.log(MessageLevel.WARNING, DEMO_BANNER)
        stageCount = len(ORDERED_STAGES)

        for index, stage in enumerate(ORDERED_STAGES):
            token.raiseIfCancelled()
            sink.stage(stage, StageState.ACTIVE)
            sink.status(f"{stage.label}...")
            sink.log(MessageLevel.INFO, f"{_PREFIX} entering stage {stage.label}")

            # wait() returns True the moment cancellation is requested, so a
            # stop is honoured immediately rather than after the full delay.
            if token.wait(self._secondsPerStage):
                token.raiseIfCancelled()

            sink.stage(stage, StageState.COMPLETED)
            sink.progress(round((index + 1) / stageCount * 100))

        sink.status("Demo run finished")
        sink.log(MessageLevel.WARNING, f"{_PREFIX} finished. All reported counts are zero by design.")

        outputDirectory = request.outputDirectory
        return ConversionOutcome(
            outputDirectory=outputDirectory if outputDirectory is not None else request.profileZip or _here(),
            excelFileCount=0,
            detectedLines=0,
            detectedSubstations=0,
            finishedAt=datetime.now(),
        )


def _here():
    from pathlib import Path

    return Path.cwd()
