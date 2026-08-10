"""The Preferences dialog.

The dialog edits a :class:`Preferences` value and hands the edited copy back. It
does not read or write settings itself, which keeps persistence in one place and
makes the dialog trivial to test.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from cgmesparser.gui.core.settings import MAX_LOG_ROWS, MIN_LOG_ROWS, Preferences


class PreferencesDialog(QDialog):
    """Edits application preferences."""

    def __init__(self, preferences: Preferences, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.setMinimumWidth(460)

        self._initial = preferences.normalised()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        session = QGroupBox("Session", self)
        sessionForm = QFormLayout(session)
        sessionForm.setSpacing(10)

        self._rememberPaths = QCheckBox("Remember the last used paths", session)
        self._rememberPaths.setToolTip(
            "Restore the four selected paths the next time the application starts."
        )
        sessionForm.addRow(self._rememberPaths)

        self._confirmOnExit = QCheckBox("Ask for confirmation before exiting", session)
        sessionForm.addRow(self._confirmOnExit)

        self._openOutput = QCheckBox("Open the output folder when a conversion finishes", session)
        sessionForm.addRow(self._openOutput)
        layout.addWidget(session)

        logging = QGroupBox("Logging", self)
        loggingForm = QFormLayout(logging)
        loggingForm.setSpacing(10)

        self._verbose = QCheckBox("Verbose logging", logging)
        self._verbose.setToolTip("Include detailed diagnostic messages in the log.")
        loggingForm.addRow(self._verbose)

        self._maxLogRows = QSpinBox(logging)
        self._maxLogRows.setRange(MIN_LOG_ROWS, MAX_LOG_ROWS)
        self._maxLogRows.setSingleStep(100)
        self._maxLogRows.setGroupSeparatorShown(True)
        loggingForm.addRow("Maximum log rows", self._maxLogRows)

        hint = QLabel("Older lines are discarded once the limit is reached.", logging)
        hint.setObjectName("messageEmpty")
        loggingForm.addRow("", hint)
        layout.addWidget(logging)

        layout.addStretch(1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        restore = buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults)
        restore.clicked.connect(self.restoreDefaults)
        layout.addWidget(buttons)

        self._apply(self._initial)

    def restoreDefaults(self) -> None:
        self._apply(Preferences())

    def preferences(self) -> Preferences:
        """The edited preferences, whether or not the dialog was accepted."""
        return Preferences(
            rememberPaths=self._rememberPaths.isChecked(),
            verboseLogging=self._verbose.isChecked(),
            maxLogRows=self._maxLogRows.value(),
            confirmOnExit=self._confirmOnExit.isChecked(),
            openOutputWhenFinished=self._openOutput.isChecked(),
        ).normalised()

    def _apply(self, preferences: Preferences) -> None:
        self._rememberPaths.setChecked(preferences.rememberPaths)
        self._confirmOnExit.setChecked(preferences.confirmOnExit)
        self._openOutput.setChecked(preferences.openOutputWhenFinished)
        self._verbose.setChecked(preferences.verboseLogging)
        self._maxLogRows.setValue(preferences.maxLogRows)
