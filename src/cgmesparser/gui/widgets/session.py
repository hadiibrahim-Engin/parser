"""The Session Info card."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from cgmesparser.gui.core.session import SessionInfo
from cgmesparser.gui.resources.tokens import TOKENS, Tokens
from cgmesparser.gui.widgets.common import Card, KeyValueRow


class SessionInfoCard(Card):
    """Who is running this, where, and with which runtime.

    Fixed for the lifetime of the process; it exists so a support request can
    quote it rather than describe it.
    """

    def __init__(self, tokens: Tokens = TOKENS, parent: QWidget | None = None) -> None:
        super().__init__("Session Info", iconName="info", accentTitle=True, tokens=tokens, parent=parent)

        self._rows = {
            "sessionId": KeyValueRow("Session ID", None, None, 120, tokens, self),
            "user": KeyValueRow("User", None, None, 120, tokens, self),
            "computer": KeyValueRow("Computer", None, None, 120, tokens, self),
            "pythonVersion": KeyValueRow("Python", None, None, 120, tokens, self),
            "pysideVersion": KeyValueRow("PySide6", None, None, 120, tokens, self),
        }
        for row in self._rows.values():
            self.addBodyWidget(row)
        self.addBodyStretch(1)

    def applySessionInfo(self, info: SessionInfo) -> None:
        self._rows["sessionId"].setValue(info.sessionId)
        self._rows["user"].setValue(info.user)
        self._rows["computer"].setValue(info.computer)
        self._rows["pythonVersion"].setValue(info.pythonVersion)
        self._rows["pysideVersion"].setValue(info.pysideVersion)

    def values(self) -> dict[str, str]:
        return {name: row.value() for name, row in self._rows.items()}
