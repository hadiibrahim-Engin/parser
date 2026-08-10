"""Small building blocks shared by the cards."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cgmesparser.gui.resources.icons import iconPixmap
from cgmesparser.gui.resources.tokens import TOKENS, Tokens

EMPTY_VALUE = "—"  # em dash: "no value yet", never a zero


def screenRatio() -> float:
    """Device pixel ratio of the primary screen, or 1.0 with no application."""
    application = QApplication.instance()
    if application is None:
        return 1.0
    screen = application.primaryScreen()
    return float(screen.devicePixelRatio()) if screen is not None else 1.0


def scaledPixmap(name: str, colour: str, size: int = 20) -> QPixmap:
    """An icon pixmap rendered for the current screen."""
    return iconPixmap(name, colour, size, screenRatio())


def iconLabel(name: str, colour: str, size: int = 20, parent: QWidget | None = None) -> QLabel:
    """A fixed-size label showing one icon."""
    label = QLabel(parent)
    label.setPixmap(scaledPixmap(name, colour, size))
    label.setFixedSize(size, size)
    label.setScaledContents(True)
    return label


def setIcon(label: QLabel, name: str, colour: str, size: int = 20) -> None:
    """Replace the icon shown by a label built with :func:`iconLabel`."""
    label.setPixmap(scaledPixmap(name, colour, size))
    label.setFixedSize(size, size)


def elide(label: QLabel, text: str, width: int) -> None:
    """Set ``text`` on ``label``, shortened in the middle to fit ``width``.

    The full text becomes the tooltip, so nothing is ever unreachable - which
    matters for paths, where the distinguishing part is often the tail.
    """
    metrics = QFontMetrics(label.font())
    label.setText(metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, max(40, width)))
    label.setToolTip(text)


class SectionBadge(QLabel):
    """The numbered square that heads each card."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("sectionBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class Card(QFrame):
    """A white rounded panel with an optional numbered badge and title."""

    def __init__(
        self,
        title: str = "",
        badge: str | None = None,
        accentTitle: bool = False,
        iconName: str | None = None,
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
            header.setSpacing(10)
            if badge is not None:
                header.addWidget(SectionBadge(badge, self))
            elif iconName is not None:
                header.addWidget(iconLabel(iconName, tokens.primary, 20, self))
            titleLabel = QLabel(title, self)
            titleLabel.setObjectName("cardTitleAccent" if accentTitle else "cardTitle")
            header.addWidget(titleLabel)
            header.addStretch(1)
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


class KeyValueRow(QWidget):
    """``icon  Label  :  Value`` - the row used by Output and Session Info.

    Starts showing :data:`EMPTY_VALUE` and stays that way until something real
    is set, so an unpopulated card can never be mistaken for a zero result.
    """

    def __init__(
        self,
        label: str,
        iconName: str | None = None,
        iconColour: str | None = None,
        labelWidth: int = 150,
        tokens: Tokens = TOKENS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tokens = tokens

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        if iconName is not None:
            layout.addWidget(iconLabel(iconName, iconColour or tokens.primary, 18, self))

        self._label = QLabel(label, self)
        self._label.setObjectName("keyLabel")
        self._label.setMinimumWidth(labelWidth)
        layout.addWidget(self._label)

        separator = QLabel(":", self)
        separator.setObjectName("keySeparator")
        layout.addWidget(separator)

        self._value = QLabel(EMPTY_VALUE, self)
        self._value.setObjectName("valueLabel")
        self._value.setProperty("empty", "true")
        self._value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
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
