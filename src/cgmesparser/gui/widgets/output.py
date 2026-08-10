"""Card 4 - the output summary and the Open Output Folder button."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton, QWidget

from cgmesparser.gui.core.result import ConversionOutcome
from cgmesparser.gui.resources.icons import icon as buildIcon
from cgmesparser.gui.resources.tokens import TOKENS, Tokens
from cgmesparser.gui.widgets.common import Card, KeyValueRow


class OutputCard(Card):
    """What the last run produced.

    Every value starts as the empty marker and only ever changes because a real
    outcome said so. There is deliberately no code path that fills these in
    optimistically.
    """

    openFolderRequested = Signal()

    def __init__(self, tokens: Tokens = TOKENS, parent: QWidget | None = None) -> None:
        super().__init__("Output", badge="4", tokens=tokens, parent=parent)
        self._tokens = tokens

        self._excelFiles = KeyValueRow("Excel files", "excel", tokens.success, 168, tokens, self)
        self._lines = KeyValueRow("Detected lines", "lines", tokens.primary, 168, tokens, self)
        self._substations = KeyValueRow(
            "Detected substations", "substation", tokens.primary, 168, tokens, self
        )
        self._lastRun = KeyValueRow("Last run", "clock", tokens.textSecondary, 168, tokens, self)

        for row in (self._excelFiles, self._lines, self._substations, self._lastRun):
            self.addBodyWidget(row)

        self.addBodyStretch(1)

        self._openFolder = QPushButton("  Open Output Folder", self)
        self._openFolder.setObjectName("linkButton")
        self._openFolder.setIcon(buildIcon("folderOpen", tokens.primary, 18))
        self._openFolder.clicked.connect(self.openFolderRequested)
        self.addBodyWidget(self._openFolder)

    # -- setters, called only from a real outcome ------------------------------

    def setExcelFileCount(self, count: int | None) -> None:
        self._excelFiles.setValue(_number(count))

    def setDetectedLines(self, count: int | None) -> None:
        self._lines.setValue(_number(count))

    def setDetectedSubstations(self, count: int | None) -> None:
        self._substations.setValue(_number(count))

    def setLastRun(self, moment: datetime | None) -> None:
        self._lastRun.setValue(_timestamp(moment))

    def applyOutcome(self, outcome: ConversionOutcome) -> None:
        self.setExcelFileCount(outcome.excelFileCount)
        self.setDetectedLines(outcome.detectedLines)
        self.setDetectedSubstations(outcome.detectedSubstations)
        self.setLastRun(outcome.finishedAt)

    def clear(self) -> None:
        for row in (self._excelFiles, self._lines, self._substations, self._lastRun):
            row.clear()

    def setOpenFolderEnabled(self, enabled: bool) -> None:
        self._openFolder.setEnabled(enabled)

    # -- introspection for tests ----------------------------------------------

    def values(self) -> dict[str, str]:
        return {
            "excelFiles": self._excelFiles.value(),
            "detectedLines": self._lines.value(),
            "detectedSubstations": self._substations.value(),
            "lastRun": self._lastRun.value(),
        }


def _number(count: int | None) -> str | None:
    if count is None:
        return None
    return f"{int(count):,}"


def _timestamp(moment: datetime | None) -> str | None:
    if moment is None:
        return None
    if moment.date() == date.today():
        return f"Today, {moment.strftime('%H:%M')}"
    return moment.strftime("%Y-%m-%d, %H:%M")
