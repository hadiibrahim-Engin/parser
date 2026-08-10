"""Card 2 - the six-stage stepper, progress bar and status line."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QWidget

from cgmesparser.gui.core.result import StageUpdate
from cgmesparser.gui.core.states import ORDERED_STAGES, ProcessingStage, StageState
from cgmesparser.gui.resources.tokens import TOKENS, Tokens
from cgmesparser.gui.widgets.common import Card

_NODE_RADIUS = 11.0
_ROW_HEIGHT = 74
_LABEL_GAP = 12
_SPIN_INTERVAL_MS = 60
_SPIN_STEP = 24  # degrees per tick


class StageStepper(QWidget):
    """Six connected nodes showing where a run has got to.

    Exactly one stage is ACTIVE at a time. The stage immediately after it is
    drawn in the accent colour as "next up", which is what gives the row its
    two-tone look without an ambiguous second active node.
    """

    def __init__(self, tokens: Tokens = TOKENS, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self._states: dict[ProcessingStage, StageState] = {}
        self._angle = 0
        self.setMinimumHeight(_ROW_HEIGHT)
        self.setMinimumWidth(560)

        # Only runs while something is active, so an idle window costs no CPU.
        self._spinner = QTimer(self)
        self._spinner.setInterval(_SPIN_INTERVAL_MS)
        self._spinner.timeout.connect(self._advanceSpinner)

        self.reset()

    # -- state ---------------------------------------------------------------

    def reset(self) -> None:
        """Return every node to PENDING."""
        self._states = {stage: StageState.PENDING for stage in ORDERED_STAGES}
        self._syncSpinner()
        self.update()

    def setStageState(self, stage: ProcessingStage, state: StageState) -> None:
        if state is StageState.ACTIVE:
            # One active node at a time: whatever was active before is done.
            for other, existing in self._states.items():
                if other is not stage and existing is StageState.ACTIVE:
                    self._states[other] = StageState.COMPLETED
        self._states[stage] = state
        self._syncSpinner()
        self.update()

    def applyUpdate(self, update: StageUpdate) -> None:
        self.setStageState(update.stage, update.state)

    def stageState(self, stage: ProcessingStage) -> StageState:
        return self._states[stage]

    def activeStage(self) -> ProcessingStage | None:
        for stage, state in self._states.items():
            if state is StageState.ACTIVE:
                return stage
        return None

    def isSpinning(self) -> bool:
        return self._spinner.isActive()

    # -- painting ------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        centres = self._nodeCentres()
        self._paintConnectors(painter, centres)
        for stage, centre in zip(ORDERED_STAGES, centres, strict=True):
            self._paintNode(painter, stage, centre)
            self._paintLabel(painter, stage, centre)
        painter.end()

    def _nodeCentres(self) -> list[QPointF]:
        count = len(ORDERED_STAGES)
        # Inset by half a label slot so the first and last captions, which are
        # centred under their node, stay inside the widget instead of clipping.
        margin = max(_NODE_RADIUS + 4, self._labelSlotWidth() / 2)
        usable = max(1.0, self.width() - 2 * margin)
        step = usable / max(1, count - 1)
        y = _NODE_RADIUS + 4
        return [QPointF(margin + index * step, y) for index in range(count)]

    def _labelSlotWidth(self) -> float:
        return max(70.0, self.width() / len(ORDERED_STAGES))

    def _paintConnectors(self, painter: QPainter, centres: list[QPointF]) -> None:
        for index in range(len(centres) - 1):
            stage = ORDERED_STAGES[index]
            colour = self._connectorColour(self._states[stage])
            painter.setPen(QPen(QColor(colour), 2.0))
            start = QPointF(centres[index].x() + _NODE_RADIUS + 3, centres[index].y())
            end = QPointF(centres[index + 1].x() - _NODE_RADIUS - 3, centres[index + 1].y())
            painter.drawLine(start, end)

    def _connectorColour(self, state: StageState) -> str:
        if state is StageState.COMPLETED:
            return self._tokens.success
        if state is StageState.ACTIVE:
            return self._tokens.primary
        if state is StageState.FAILED:
            return self._tokens.error
        return self._tokens.stepperPending

    def _paintNode(self, painter: QPainter, stage: ProcessingStage, centre: QPointF) -> None:
        state = self._states[stage]
        box = QRectF(
            centre.x() - _NODE_RADIUS, centre.y() - _NODE_RADIUS, _NODE_RADIUS * 2, _NODE_RADIUS * 2
        )

        if state is StageState.COMPLETED:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._tokens.success))
            painter.drawEllipse(box)
            self._paintTick(painter, centre)
            return

        if state is StageState.FAILED:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._tokens.error))
            painter.drawEllipse(box)
            self._paintCross(painter, centre)
            return

        if state is StageState.ACTIVE:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(self._tokens.track), 2.4))
            painter.drawEllipse(box)
            pen = QPen(QColor(self._tokens.primary), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            # Qt measures arcs in sixteenths of a degree.
            painter.drawArc(box, -self._angle * 16, 100 * 16)
            return

        if self._isNextUp(stage):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._tokens.primary))
            painter.drawEllipse(box)
            return

        painter.setBrush(QColor(self._tokens.cardBackground))
        painter.setPen(QPen(QColor(self._tokens.stepperPending), 2.0))
        painter.drawEllipse(box)

    def _isNextUp(self, stage: ProcessingStage) -> bool:
        active = self.activeStage()
        return active is not None and stage.position == active.position + 1

    def _paintTick(self, painter: QPainter, centre: QPointF) -> None:
        pen = QPen(QColor(self._tokens.cardBackground), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(
            [
                QPointF(centre.x() - 4.6, centre.y() + 0.4),
                QPointF(centre.x() - 1.4, centre.y() + 3.6),
                QPointF(centre.x() + 5.0, centre.y() - 3.4),
            ]
        )

    def _paintCross(self, painter: QPainter, centre: QPointF) -> None:
        pen = QPen(QColor(self._tokens.cardBackground), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(
            QPointF(centre.x() - 3.6, centre.y() - 3.6), QPointF(centre.x() + 3.6, centre.y() + 3.6)
        )
        painter.drawLine(
            QPointF(centre.x() + 3.6, centre.y() - 3.6), QPointF(centre.x() - 3.6, centre.y() + 3.6)
        )

    def _paintLabel(self, painter: QPainter, stage: ProcessingStage, centre: QPointF) -> None:
        state = self._states[stage]
        font = QFont(self.font())
        highlighted = state is StageState.ACTIVE or self._isNextUp(stage)
        font.setBold(highlighted or state is StageState.COMPLETED)
        font.setPointSizeF(max(8.0, self.font().pointSizeF() - 0.5))
        painter.setFont(font)
        painter.setPen(QColor(self._labelColour(stage, state, highlighted)))

        metrics = QFontMetrics(font)
        top = centre.y() + _NODE_RADIUS + _LABEL_GAP
        width = self._labelSlotWidth()
        box = QRectF(centre.x() - width / 2, top, width, metrics.height() * 2 + 2)
        painter.drawText(
            box,
            int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
            stage.label,
        )

    def _labelColour(self, stage: ProcessingStage, state: StageState, highlighted: bool) -> str:
        if state is StageState.FAILED:
            return self._tokens.error
        if highlighted:
            return self._tokens.primary
        if state is StageState.COMPLETED:
            return self._tokens.textPrimary
        return self._tokens.textMuted

    # -- spinner -------------------------------------------------------------

    def _syncSpinner(self) -> None:
        shouldSpin = self.activeStage() is not None
        if shouldSpin and not self._spinner.isActive():
            self._spinner.start()
        elif not shouldSpin and self._spinner.isActive():
            self._spinner.stop()
            self._angle = 0

    def _advanceSpinner(self) -> None:
        self._angle = (self._angle + _SPIN_STEP) % 360
        self.update()


class ProcessingCard(Card):
    """Card 2: stepper, progress bar and the one-line status."""

    def __init__(self, tokens: Tokens = TOKENS, parent: QWidget | None = None) -> None:
        super().__init__("Processing", badge="2", tokens=tokens, parent=parent)
        self._tokens = tokens

        self._stepper = StageStepper(tokens, self)
        self.addBodyWidget(self._stepper)

        progressRow = QWidget(self)
        progressLayout = QHBoxLayout(progressRow)
        progressLayout.setContentsMargins(0, 0, 0, 0)
        progressLayout.setSpacing(14)

        self._progress = QProgressBar(progressRow)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        progressLayout.addWidget(self._progress, 1)

        self._progressLabel = QLabel("0%", progressRow)
        self._progressLabel.setObjectName("progressLabel")
        self._progressLabel.setMinimumWidth(46)
        self._progressLabel.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        progressLayout.addWidget(self._progressLabel)
        self.addBodyWidget(progressRow)

        statusRow = QWidget(self)
        statusLayout = QHBoxLayout(statusRow)
        statusLayout.setContentsMargins(0, 0, 0, 0)
        statusLayout.setSpacing(8)

        caption = QLabel("Status:", statusRow)
        caption.setObjectName("statusCaption")
        statusLayout.addWidget(caption)

        self._status = QLabel("Idle", statusRow)
        self._status.setObjectName("statusText")
        statusLayout.addWidget(self._status, 1)
        self.addBodyWidget(statusRow)

    @property
    def stepper(self) -> StageStepper:
        return self._stepper

    def setProgress(self, percentage: int) -> None:
        clamped = max(0, min(100, int(percentage)))
        self._progress.setValue(clamped)
        self._progressLabel.setText(f"{clamped}%")

    def progress(self) -> int:
        return self._progress.value()

    def setStatus(self, text: str) -> None:
        self._status.setText(text)

    def status(self) -> str:
        return self._status.text()

    def applyStageUpdate(self, update: StageUpdate) -> None:
        self._stepper.applyUpdate(update)

    def reset(self) -> None:
        """Clear the stepper, progress and status back to their idle look."""
        self._stepper.reset()
        self.setProgress(0)
        self.setStatus("Idle")
