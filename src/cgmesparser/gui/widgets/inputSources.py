"""Card 1 - the four path selectors and the validation summary strip."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.states import ORDERED_ROLES, InputRole
from cgmesparser.gui.core.validation import InputCheck, ValidationReport
from cgmesparser.gui.resources.tokens import TOKENS, Tokens
from cgmesparser.gui.widgets.common import Card, repolish

_EDIT_SETTLE_MS = 400

def droppedPath(mimeData: QMimeData) -> Path | None:
    """The single local path a drop carries, or ``None`` if it carries no such thing.

    Deliberately indifferent to whether the path is a file or a directory, and
    to what the row expects. Accepting a drop is an affordance; deciding whether
    the path is usable belongs to ``validateRequest`` and is not repeated here,
    so a folder dropped on the ZIP row is taken and then reported as ``Not a
    file`` rather than silently refused.
    """
    if not mimeData.hasUrls():
        return None
    urls = mimeData.urls()
    if len(urls) != 1:
        return None
    url = urls[0]
    if not url.isLocalFile():
        return None
    local = url.toLocalFile()
    return Path(local) if local else None


class PathSelectorRow(QFrame):
    """One labelled path field with a Browse button.

    Owning its own file dialog and accepting drops is presentation, and stays
    here. Judging whether the chosen path is usable is not, and does not: the
    row simply announces what the user picked.
    """

    pathChanged = Signal(object, object)  # InputRole, Path | None

    def __init__(
        self,
        role: InputRole,
        chooseDirectory: bool = False,
        nameFilter: str = "",
        labelWidth: int = 190,
        tokens: Tokens = TOKENS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("inputSourceRow")
        self._role = role
        self._chooseDirectory = chooseDirectory
        self._nameFilter = nameFilter
        self._tokens = tokens
        self._current: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 11, 12, 12)
        layout.setSpacing(8)

        heading = QHBoxLayout()
        heading.setSpacing(8)

        label = QLabel(role.label, self)
        label.setObjectName("inputLabel")
        label.setToolTip(role.label)
        heading.addWidget(label, 1)

        layout.addLayout(heading)

        control = QHBoxLayout()
        control.setSpacing(8)

        self._edit = QLineEdit(self)
        self._edit.setPlaceholderText(_placeholderFor(role))
        self._edit.setClearButtonEnabled(False)
        self._edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        control.addWidget(self._edit, 1)

        self._browse = QPushButton("Choose", self)
        self._browse.setObjectName("browseButton")
        self._browse.setMinimumWidth(84)
        control.addWidget(self._browse)
        layout.addLayout(control)

        # Typing or pasting a path is settled before it is announced, so one
        # keystroke does not invalidate a validation six times.
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(_EDIT_SETTLE_MS)

        self._browse.clicked.connect(self._openDialog)
        self._edit.textEdited.connect(lambda _: self._settle.start())
        self._edit.editingFinished.connect(self._emitFromText)
        self._settle.timeout.connect(self._emitFromText)

        # The whole row is the drop target, not just the field, so the icon and
        # label are aimable too. The line edit would otherwise consume the drop
        # itself and paste the URL as text.
        self.setAcceptDrops(True)
        self._edit.setAcceptDrops(False)

    @property
    def role(self) -> InputRole:
        return self._role

    def path(self) -> Path | None:
        return self._current

    def setPath(self, path: Path | None, announce: bool = False) -> None:
        """Show ``path`` without emitting, unless ``announce`` is set.

        Restoring saved settings uses the quiet form; anything the user did uses
        the announcing form.
        """
        self._current = path
        text = str(path) if path is not None else ""
        if self._edit.text() != text:
            self._edit.setText(text)
        self._edit.setToolTip(text)
        if announce:
            self.pathChanged.emit(self._role, path)

    def setEditable(self, editable: bool) -> None:
        self._edit.setEnabled(editable)
        self._browse.setEnabled(editable)

    def _openDialog(self) -> None:
        start = str(self._current) if self._current is not None else ""
        if self._chooseDirectory:
            chosen = QFileDialog.getExistingDirectory(self, f"Select {self._role.label}", start)
        else:
            chosen, _ = QFileDialog.getOpenFileName(
                self, f"Select {self._role.label}", start, self._nameFilter
            )
        if chosen:
            self._settle.stop()
            self.setPath(Path(chosen), announce=True)

    def _emitFromText(self) -> None:
        self._settle.stop()
        text = self._edit.text().strip()
        candidate = Path(text) if text else None
        if candidate == self._current:
            return
        self.setPath(candidate, announce=True)

    # -- drag and drop --------------------------------------------------------

    def _setDropActive(self, active: bool) -> None:
        self._edit.setProperty("dropActive", "true" if active else "false")
        repolish(self._edit)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._edit.isEnabled() and droppedPath(event.mimeData()) is not None:
            event.acceptProposedAction()
            self._setDropActive(True)
            return
        event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._edit.isEnabled() and droppedPath(event.mimeData()) is not None:
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._setDropActive(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._setDropActive(False)
        path = droppedPath(event.mimeData())
        if path is None or not self._edit.isEnabled():
            event.ignore()
            return
        event.acceptProposedAction()
        self._settle.stop()
        self.setPath(path, announce=True)


class ValidationStrip(QFrame):
    """The verdict pill plus one line per checked input."""

    def __init__(self, tokens: Tokens = TOKENS, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("validationStrip")
        self._tokens = tokens

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(14)

        self._verdict = QLabel("Not validated", self)
        self._verdict.setObjectName("validationVerdict")
        self._verdict.setMinimumWidth(132)
        layout.addWidget(self._verdict)

        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(26)
        self._grid.setVerticalSpacing(6)
        layout.addLayout(self._grid, 1)

        self._rows: list[QWidget] = []
        self.clear()

    def clear(self) -> None:
        """Return to the neutral, pre-validation appearance."""
        self._clearGrid()
        self._applyTone("neutral")
        self._verdict.setText("Not validated")
        hint = QLabel("Select all four inputs, then choose Validate Inputs.", self)
        hint.setObjectName("checkText")
        self._grid.addWidget(hint, 0, 0)
        self._rows.append(hint)

    def applyReport(self, report: ValidationReport) -> None:
        """Render ``report``: verdict on the left, one entry per check on the right."""
        self._clearGrid()

        tone = "ok" if report.isValid else "error"
        self._applyTone(tone)
        self._verdict.setText(report.summary)

        # Two columns, filled top-to-bottom so the reading order matches the
        # order the inputs appear in above.
        checks = list(report.checks)
        rowCount = (len(checks) + 1) // 2
        for index, check in enumerate(checks):
            row = index % rowCount if rowCount else 0
            column = index // rowCount if rowCount else 0
            entry = self._buildEntry(check)
            self._grid.addWidget(entry, row, column)
            self._rows.append(entry)

    def _buildEntry(self, check: InputCheck) -> QWidget:
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        text = QLabel(f"{check.role.label}: {check.message}", holder)
        text.setObjectName("checkText")
        text.setProperty("tone", check.status.value)
        row.addWidget(text)
        row.addStretch(1)
        return holder

    def _applyTone(self, tone: str) -> None:
        for widget in (self, self._verdict):
            widget.setProperty("tone", tone)
            repolish(widget)

    def _clearGrid(self) -> None:
        for widget in self._rows:
            self._grid.removeWidget(widget)
            # Reparenting is what actually stops it being painted; deleteLater
            # alone leaves the old widget on screen until the event loop runs.
            widget.setParent(None)
            widget.deleteLater()
        self._rows.clear()


class InputSourcesCard(Card):
    """Card 1: the four selectors above the validation strip."""

    pathChanged = Signal(object, object)  # InputRole, Path | None

    def __init__(self, tokens: Tokens = TOKENS, parent: QWidget | None = None) -> None:
        super().__init__(
            "Input Sources",
            description="Choose the profile, source datasets, and output destination.",
            tokens=tokens,
            parent=parent,
        )

        self._rows: dict[InputRole, PathSelectorRow] = {}
        selectorGrid = QGridLayout()
        selectorGrid.setContentsMargins(0, 0, 0, 0)
        selectorGrid.setHorizontalSpacing(tokens.gridGap)
        selectorGrid.setVerticalSpacing(tokens.gridGap)
        for index, role in enumerate(ORDERED_ROLES):
            row = PathSelectorRow(
                role,
                chooseDirectory=role is not InputRole.PROFILE_ZIP,
                nameFilter="ZIP archives (*.zip);;All files (*)" if role is InputRole.PROFILE_ZIP else "",
                tokens=tokens,
                parent=self,
            )
            row.pathChanged.connect(self.pathChanged)
            self._rows[role] = row
            selectorGrid.addWidget(row, index // 2, index % 2)

        selectorGrid.setColumnStretch(0, 1)
        selectorGrid.setColumnStretch(1, 1)
        self.bodyLayout.addLayout(selectorGrid)

        self._strip = ValidationStrip(tokens, self)
        self.addBodyWidget(self._strip)

    def applyRequest(self, request: ConversionRequest) -> None:
        """Show the paths in ``request`` without announcing them back."""
        for role, row in self._rows.items():
            row.setPath(request.pathFor(role), announce=False)

    def applyReport(self, report: ValidationReport) -> None:
        self._strip.applyReport(report)

    def clearReport(self) -> None:
        self._strip.clear()

    def setEditable(self, editable: bool) -> None:
        for row in self._rows.values():
            row.setEditable(editable)

    def rowFor(self, role: InputRole) -> PathSelectorRow:
        return self._rows[role]


def _placeholderFor(role: InputRole) -> str:
    if role is InputRole.PROFILE_ZIP:
        return "Drop or select a CGMES profile .zip archive"
    if role is InputRole.OUTPUT_DIRECTORY:
        return "Drop or select where the Excel output should be written"
    return "Drop or select a dataset directory"
