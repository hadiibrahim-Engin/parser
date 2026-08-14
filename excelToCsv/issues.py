"""Collecting and formatting business findings (errors / warnings).

The central error strategy:

* ``WARNING`` - tolerable, the conversion carries on.
* ``ERROR``   - ALWAYS fatal. Every error of a phase is collected and logged in
  full, then the conversion aborts BEFORE any CSV file comes into existence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from excelToCsv.errors import ConversionError

#: How an empty value is rendered in log messages.
EMPTY_DISPLAY = "<empty>"


def formatValue(value: object) -> str:
    """Render a cell value for log output; empty values become ``<empty>``."""
    if value is None:
        return EMPTY_DISPLAY
    text = str(value).strip()
    return text if text else EMPTY_DISPLAY


@dataclass(frozen=True, slots=True)
class Issue:
    """A single finding with the full context needed to trace it back to Excel."""

    problem: str
    row: int | None = None
    elementId: str = ""
    elementType: str = ""
    field: str = ""
    value: object = None
    expected: str = ""
    action: str = ""

    def render(self, headline: str) -> str:
        """Build the multi-line log block for this finding."""
        lines = [headline]
        if self.row is not None:
            lines.append(f"Row: {self.row}")
        if self.elementId:
            lines.append(f"ELEMENT ID: {self.elementId}")
        if self.elementType:
            lines.append(f"ELEMENT-TYPE: {self.elementType}")
        if self.field:
            lines.append(f"Field: {self.field}")
            lines.append(f"Value: {formatValue(self.value)}")
        lines.append(f"Problem: {self.problem}")
        if self.expected:
            lines.append(f"Expected: {self.expected}")
        if self.action:
            lines.append(f"Action: {self.action}")
        return "\n".join(lines)


@dataclass(slots=True)
class IssueCollector:
    """Collect errors and warnings and force the abort at phase boundaries.

    Errors are logged immediately (so the user sees them live) but only turned
    into a :class:`ConversionError` at a defined phase boundary via
    :meth:`abortIfFailed`. That way one run surfaces ALL problems instead of
    just the first.
    """

    logger: logging.Logger
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    maxLoggedErrors: int = 200

    def error(self, problem: str, **context: object) -> None:
        """Record a fatal finding and log it immediately.

        ``stacklevel=2`` makes the source location in the log point at the
        calling domain module (e.g. ``stations.py``) instead of this file.
        """
        issue = Issue(problem=problem, **context)  # type: ignore[arg-type]
        self.errors.append(issue)
        if len(self.errors) <= self.maxLoggedErrors:
            self.logger.error(issue.render("Validation failed."), stacklevel=2)
        elif len(self.errors) == self.maxLoggedErrors + 1:
            self.logger.error(
                "Further errors are suppressed after %d entries.",
                self.maxLoggedErrors,
                stacklevel=2,
            )

    def warning(self, problem: str, **context: object) -> None:
        """Record a tolerable finding and log it immediately."""
        issue = Issue(problem=problem, **context)  # type: ignore[arg-type]
        self.warnings.append(issue)
        self.logger.warning(issue.render("Tolerable issue."), stacklevel=2)

    @property
    def failed(self) -> bool:
        """``True`` as soon as at least one fatal error has been recorded."""
        return bool(self.errors)

    def abortIfFailed(self, phase: str) -> None:
        """Abort the conversion when this phase produced any error."""
        if not self.errors:
            return
        count = len(self.errors)
        self.logger.critical(
            "Conversion aborted in phase '%s': %d fatal error%s. No CSV files were written.",
            phase,
            count,
            "" if count == 1 else "s",
            stacklevel=2,
        )
        raise ConversionError(f"{count} fatal error(s) during phase '{phase}'")
