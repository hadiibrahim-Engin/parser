"""The restrained title bar across the top of the window."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from cgmesparser.gui.resources.tokens import TOKENS, Tokens


class HeaderBanner(QWidget):
    """A text-first application header without ornamental graphics."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        tokens: Tokens = TOKENS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("headerBanner")
        self.setFixedHeight(76)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(26, 10, 26, 10)

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
