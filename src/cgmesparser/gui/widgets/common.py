"""Small building blocks shared by the cards."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cgmesparser.gui.resources.tokens import TOKENS, Tokens

EMPTY_VALUE = "—"  # em dash: "no value yet", never a zero


def elide(label: QLabel, text: str, width: int) -> None:
    """Set ``text`` on ``label``, shortened in the middle to fit ``width``.

    The full text becomes the tooltip, so nothing is ever unreachable - which
    matters for paths, where the distinguishing part is often the tail.
    """
    metrics = QFontMetrics(label.font())
    label.setText(metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, max(40, width)))
    label.setToolTip(text)


class Card(QFrame):
    """A raised workspace panel with a title and optional description."""

    def __init__(
        self,
        title: str = "",
        description: str = "",
        tokens: Tokens = TOKENS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._tokens = tokens

        padding = tokens.cardPadding
        outer = QVBoxLayout(self)
        outer.setContentsMargins(padding, padding, padding, padding)
        outer.setSpacing(tokens.gridGap)

        if title:
            header = QHBoxLayout()
            header.setSpacing(0)

            text = QVBoxLayout()
            text.setContentsMargins(0, 0, 0, 0)
            text.setSpacing(2)
            titleLabel = QLabel(title, self)
            titleLabel.setObjectName("cardTitle")
            text.addWidget(titleLabel)
            if description:
                descriptionLabel = QLabel(description, self)
                descriptionLabel.setObjectName("cardDescription")
                descriptionLabel.setWordWrap(True)
                text.addWidget(descriptionLabel)
            header.addLayout(text, 1)
            self._headerLayout = header
            outer.addLayout(header)
        else:
            self._headerLayout = QHBoxLayout()

        self._body = QVBoxLayout()
        self._body.setSpacing(tokens.gridGap)
        outer.addLayout(self._body)
        self._outer = outer

    @property
    def bodyLayout(self) -> QVBoxLayout:
        return self._body

    @property
    def headerLayout(self) -> QHBoxLayout:
        """The title row, for adding a trailing control such as a Clear button."""
        return self._headerLayout

    def addBodyWidget(self, widget: QWidget, stretch: int = 0) -> None:
        self._body.addWidget(widget, stretch)

    def addBodyStretch(self, stretch: int = 1) -> None:
        self._body.addStretch(stretch)


class KeyValueRow(QFrame):
    """``Label  Value`` - the compact row used by Output and Session Info.

    Starts showing :data:`EMPTY_VALUE` and stays that way until something real
    is set, so an unpopulated card can never be mistaken for a zero result.
    """

    def __init__(
        self,
        label: str,
        labelWidth: int = 150,
        tokens: Tokens = TOKENS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("keyValueRow")
        self._tokens = tokens

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        self._label = QLabel(label, self)
        self._label.setObjectName("keyLabel")
        self._label.setMinimumWidth(min(86, labelWidth))
        layout.addWidget(self._label)

        self._value = QLabel(EMPTY_VALUE, self)
        self._value.setObjectName("valueLabel")
        self._value.setProperty("empty", "true")
        self._value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._value, 1)

    def setValue(self, text: str | None) -> None:
        """Show ``text``, or the empty marker when it is None or blank."""
        isEmpty = text is None or text == ""
        self._value.setText(EMPTY_VALUE if isEmpty else str(text))
        self._value.setProperty("empty", "true" if isEmpty else "false")
        self._value.setToolTip("" if isEmpty else str(text))
        _repolish(self._value)

    def value(self) -> str:
        return self._value.text()

    def clear(self) -> None:
        self.setValue(None)


def _repolish(widget: QWidget) -> None:
    """Re-apply the stylesheet after a dynamic property changed.

    Qt only consults dynamic properties in selectors when the style is
    re-evaluated, which does not happen on its own.
    """
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def repolish(widget: QWidget) -> None:
    _repolish(widget)
