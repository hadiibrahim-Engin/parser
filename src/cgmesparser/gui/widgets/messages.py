"""Card 3 - the message log, split into Log / Warnings / Errors."""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QPushButton,
    QTableView,
    QTabWidget,
    QWidget,
)

from cgmesparser.gui.core.result import LogRecord
from cgmesparser.gui.core.settings import DEFAULT_LOG_ROWS
from cgmesparser.gui.core.states import MessageLevel
from cgmesparser.gui.resources.tokens import TOKENS, Tokens
from cgmesparser.gui.widgets.common import Card

_TIME_COLUMN = 0
_MESSAGE_COLUMN = 1
_COLUMN_COUNT = 2

_LEVEL_ROLE = int(Qt.ItemDataRole.UserRole) + 1

# Qt's model interface defaults these arguments to an invalid index. Building it
# once at import time keeps that default out of the function signature.
_NO_PARENT = QModelIndex()

def levelColour(level: MessageLevel, tokens: Tokens = TOKENS) -> str:
    return {
        MessageLevel.INFO: tokens.primary,
        MessageLevel.WARNING: tokens.warning,
        MessageLevel.ERROR: tokens.error,
    }[level]


class MessageLogModel(QAbstractTableModel):
    """A bounded, append-only table of log records.

    Capped as a ring buffer so a chatty backend cannot exhaust memory; the
    oldest lines are dropped first.
    """

    countsChanged = Signal()

    def __init__(self, maxRows: int = DEFAULT_LOG_ROWS, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._records: deque[LogRecord] = deque(maxlen=max(1, maxRows))
        self._tokens = TOKENS

    # -- Qt model interface ---------------------------------------------------

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = _NO_PARENT) -> int:
        return 0 if parent.isValid() else len(self._records)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _NO_PARENT) -> int:
        return 0 if parent.isValid() else _COLUMN_COUNT

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        record = self._records[index.row()]

        if role == _LEVEL_ROLE:
            return record.level.value

        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == _TIME_COLUMN:
                return record.clockTime
            if index.column() == _MESSAGE_COLUMN:
                return record.message
            return None

        if role == Qt.ItemDataRole.ForegroundRole:
            if index.column() == _TIME_COLUMN:
                return QColor(self._tokens.textMuted)
            if record.level is MessageLevel.ERROR:
                return QColor(self._tokens.error)
            if record.level is MessageLevel.WARNING:
                return QColor(self._tokens.warning)
            return QColor(self._tokens.textPrimary)

        if role == Qt.ItemDataRole.FontRole and index.column() == _TIME_COLUMN:
            font = QFont()
            font.setStyleHint(QFont.StyleHint.Monospace)
            return font

        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{record.clockTime}  {record.level.value}  {record.message}"

        return None

    # -- content --------------------------------------------------------------

    def append(self, record: LogRecord) -> None:
        atCapacity = self._records.maxlen is not None and len(self._records) == self._records.maxlen
        if atCapacity:
            # A full ring buffer both drops a row and gains one; a plain insert
            # would leave the view's row indices one ahead of the model's.
            self.beginRemoveRows(QModelIndex(), 0, 0)
            self._records.popleft()
            self.endRemoveRows()

        row = len(self._records)
        self.beginInsertRows(QModelIndex(), row, row)
        self._records.append(record)
        self.endInsertRows()
        self.countsChanged.emit()

    def clear(self) -> None:
        if not self._records:
            return
        self.beginResetModel()
        self._records.clear()
        self.endResetModel()
        self.countsChanged.emit()

    def setMaxRows(self, maxRows: int) -> None:
        limit = max(1, int(maxRows))
        if self._records.maxlen == limit:
            return
        self.beginResetModel()
        self._records = deque(self._records, maxlen=limit)
        self.endResetModel()
        self.countsChanged.emit()

    def records(self) -> tuple[LogRecord, ...]:
        return tuple(self._records)

    def countFor(self, level: MessageLevel) -> int:
        return sum(1 for record in self._records if record.level is level)


class LevelFilterProxy(QSortFilterProxyModel):
    """Shows every row, or only those of one level."""

    def __init__(self, level: MessageLevel | None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._level = level

    def filterAcceptsRow(
        self, sourceRow: int, sourceParent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        if self._level is None:
            return True
        model = self.sourceModel()
        if model is None:
            return False
        value = model.data(model.index(sourceRow, 0, sourceParent), _LEVEL_ROLE)
        return value == self._level.value


class _LogView(QTableView):
    """A borderless table that follows the tail unless the user scrolled away."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setShowGrid(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.setMinimumHeight(110)

    def setModel(self, model) -> None:
        super().setModel(model)
        if model is None:
            return
        header = self.horizontalHeader()
        header.setSectionResizeMode(_TIME_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_MESSAGE_COLUMN, QHeaderView.ResizeMode.Stretch)
        model.rowsInserted.connect(self._followTail)

    def _followTail(self) -> None:
        scrollBar = self.verticalScrollBar()
        # Only auto-scroll when the user was already at the bottom, so reading
        # back through history is never yanked away.
        if scrollBar.value() >= scrollBar.maximum() - 2:
            self.scrollToBottom()


class MessagesCard(Card):
    """Card 3: the log, its level tabs and the Clear button."""

    clearRequested = Signal()

    def __init__(
        self,
        maxRows: int = DEFAULT_LOG_ROWS,
        tokens: Tokens = TOKENS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "Messages",
            description="Validation feedback and conversion activity.",
            tokens=tokens,
            parent=parent,
        )
        self._tokens = tokens

        self._model = MessageLogModel(maxRows, self)

        self._clear = QPushButton("Clear", self)
        self._clear.setObjectName("ghostButton")
        self._clear.setMaximumWidth(110)
        self.headerLayout.addWidget(self._clear)

        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        self._tabs.tabBar().setExpanding(False)

        self._views: dict[MessageLevel | None, _LogView] = {}
        for level, title in (
            (None, "Log"),
            (MessageLevel.WARNING, "Warnings"),
            (MessageLevel.ERROR, "Errors"),
        ):
            proxy = LevelFilterProxy(level, self)
            proxy.setSourceModel(self._model)
            view = _LogView(self)
            view.setModel(proxy)
            self._views[level] = view
            self._tabs.addTab(view, title)

        self.addBodyWidget(self._tabs, 1)

        self._clear.clicked.connect(self._onClear)
        self._model.countsChanged.connect(self._refreshTabTitles)
        self._refreshTabTitles()

    # -- content --------------------------------------------------------------

    def append(self, record: LogRecord) -> None:
        self._model.append(record)

    def appendMany(self, records) -> None:
        for record in records:
            self._model.append(record)

    def clear(self) -> None:
        self._model.clear()

    def setMaxRows(self, maxRows: int) -> None:
        self._model.setMaxRows(maxRows)

    # -- introspection, used by tests and the controller ----------------------

    @property
    def model(self) -> MessageLogModel:
        return self._model

    def viewFor(self, level: MessageLevel | None) -> _LogView:
        return self._views[level]

    def tabTitles(self) -> tuple[str, ...]:
        return tuple(self._tabs.tabText(index) for index in range(self._tabs.count()))

    def visibleRowCount(self, level: MessageLevel | None) -> int:
        model = self._views[level].model()
        return 0 if model is None else model.rowCount()

    # -- internals ------------------------------------------------------------

    def _onClear(self) -> None:
        self._model.clear()
        self.clearRequested.emit()

    def _refreshTabTitles(self) -> None:
        self._tabs.setTabText(0, "Log")
        self._tabs.setTabText(1, f"Warnings ({self._model.countFor(MessageLevel.WARNING)})")
        self._tabs.setTabText(2, f"Errors ({self._model.countFor(MessageLevel.ERROR)})")
