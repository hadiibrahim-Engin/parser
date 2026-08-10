"""The bar of primary actions along the bottom of the window."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from cgmesparser.gui.core.transitions import ButtonStates
from cgmesparser.gui.resources.tokens import TOKENS, Tokens


class ActionBar(QFrame):
    """Preferences, Validate Inputs, Start Conversion, Stop, Exit.

    :meth:`applyButtonStates` is the only place any of these buttons is enabled
    or disabled. Nothing else in the application calls ``setEnabled`` on them.
    """

    preferencesRequested = Signal()
    validateRequested = Signal()
    startRequested = Signal()
    stopRequested = Signal()
    exitRequested = Signal()

    def __init__(self, tokens: Tokens = TOKENS, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("actionBar")
        self._tokens = tokens

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 11, 24, 11)
        layout.setSpacing(10)

        self._preferences = self._button("Preferences")
        self._validate = self._button("Validate Inputs", "accentButton")
        self._start = self._button("Start Conversion", "primaryButton")
        self._stop = self._button("Stop")
        self._exit = self._button("Exit")

        self._preferences.setMinimumWidth(132)
        self._validate.setMinimumWidth(154)
        self._start.setMinimumWidth(188)
        self._stop.setMinimumWidth(104)
        self._exit.setMinimumWidth(88)

        layout.addWidget(self._preferences)
        layout.addStretch(1)
        layout.addWidget(self._validate)
        layout.addWidget(self._start)
        layout.addWidget(self._stop)
        layout.addSpacing(8)
        layout.addWidget(self._exit)

        self._preferences.clicked.connect(self.preferencesRequested)
        self._validate.clicked.connect(self.validateRequested)
        self._start.clicked.connect(self.startRequested)
        self._stop.clicked.connect(self.stopRequested)
        self._exit.clicked.connect(self.exitRequested)

    def _button(self, text: str, objectName: str = "") -> QPushButton:
        button = QPushButton(text, self)
        if objectName:
            button.setObjectName(objectName)
        return button

    def applyButtonStates(self, states: ButtonStates) -> None:
        self._preferences.setEnabled(states.preferences)
        self._validate.setEnabled(states.validate)
        self._start.setEnabled(states.start)
        self._stop.setEnabled(states.stop)
        self._exit.setEnabled(states.exit)

    def enabledStates(self) -> dict[str, bool]:
        """The current enabled flags, for assertions in tests."""
        return {
            "preferences": self._preferences.isEnabled(),
            "validate": self._validate.isEnabled(),
            "start": self._start.isEnabled(),
            "stop": self._stop.isEnabled(),
            "exit": self._exit.isEnabled(),
        }

    def buttonFor(self, name: str) -> QPushButton:
        return {
            "preferences": self._preferences,
            "validate": self._validate,
            "start": self._start,
            "stop": self._stop,
            "exit": self._exit,
        }[name]
