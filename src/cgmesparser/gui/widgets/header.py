"""The title banner across the top of the window."""

from __future__ import annotations

import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from cgmesparser.gui.resources.tokens import TOKENS, Tokens
from cgmesparser.gui.widgets.common import iconLabel

_MOTIF_SEED = 20250513  # fixed, so the decorative circuit pattern never shuffles


class HeaderBanner(QWidget):
    """Gradient banner with the product mark, title and subtitle.

    The circuit motif on the right is painted rather than shipped as an image:
    it scales to any width and costs nothing to bundle.
    """

    def __init__(
        self,
        title: str,
        subtitle: str,
        tokens: Tokens = TOKENS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens
        self.setObjectName("headerBanner")
        self.setFixedHeight(106)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(18)

        layout.addWidget(iconLabel("tower", tokens.primary, 62, self))

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addStretch(1)

        self._title = QLabel(title, self)
        self._title.setObjectName("headerTitle")
        text.addWidget(self._title)

        self._subtitle = QLabel(subtitle, self)
        self._subtitle.setObjectName("headerSubtitle")
        text.addWidget(self._subtitle)
        text.addStretch(1)

        layout.addLayout(text)
        layout.addStretch(1)

        self._motif = _buildMotif()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        area = QRectF(self.rect())
        gradient = QLinearGradient(area.topLeft(), area.topRight())
        gradient.setColorAt(0.0, QColor(self._tokens.headerGradientStart))
        gradient.setColorAt(1.0, QColor(self._tokens.headerGradientEnd))
        painter.fillRect(area, gradient)

        self._paintMotif(painter, area)

        painter.setPen(QPen(QColor(self._tokens.cardBorder), 1))
        painter.drawLine(area.bottomLeft(), area.bottomRight())
        painter.end()

    def _paintMotif(self, painter: QPainter, area: QRectF) -> None:
        """Draw the decorative circuit traces in the right-hand third."""
        motifWidth = area.width() * 0.42
        if motifWidth < 120:
            return

        left = area.right() - motifWidth
        colour = QColor(self._tokens.headerMotif)
        painter.save()
        painter.setClipRect(QRectF(left, area.top(), motifWidth, area.height()))

        painter.setPen(QPen(colour, 1.2))
        for trace in self._motif["traces"]:
            points = [QPointF(left + x * motifWidth, area.top() + y * area.height()) for x, y in trace]
            for start, end in zip(points, points[1:], strict=False):
                painter.drawLine(start, end)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        for x, y, radius in self._motif["nodes"]:
            painter.drawEllipse(
                QPointF(left + x * motifWidth, area.top() + y * area.height()), radius, radius
            )
        painter.restore()


def _buildMotif() -> dict[str, list]:
    """Generate the circuit pattern once, deterministically.

    A fixed seed means the banner looks identical on every launch and in every
    screenshot; a random one would make visual diffs useless.
    """
    generator = random.Random(_MOTIF_SEED)
    traces: list[list[tuple[float, float]]] = []
    nodes: list[tuple[float, float, float]] = []

    for _ in range(14):
        x = generator.uniform(0.05, 0.95)
        y = generator.uniform(0.08, 0.92)
        trace = [(x, y)]
        for _ in range(generator.randint(2, 4)):
            if generator.random() < 0.5:
                x = min(0.98, max(0.02, x + generator.uniform(-0.22, 0.22)))
            else:
                y = min(0.96, max(0.04, y + generator.uniform(-0.3, 0.3)))
            trace.append((x, y))
        traces.append(trace)
        nodes.append((x, y, generator.choice([2.0, 2.6, 3.4])))

    return {"traces": traces, "nodes": nodes}
