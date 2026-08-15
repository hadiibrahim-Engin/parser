"""Collecting and formatting business findings (errors / warnings).

The central error strategy:

* ``WARNING`` - tolerable, the conversion carries on.
* ``ERROR``   - ALWAYS fatal. Every error of a phase is collected and logged in
  full, then the conversion aborts BEFORE any CSV file comes into existence.
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from excelToCsv.errors import ConversionError

#: How an empty value is rendered in log messages.
EMPTY_DISPLAY = "<empty>"

SEVERITY_ERROR: Final = "ERROR"
SEVERITY_WARNING: Final = "WARNING"

#: Column order of the issue report; ``Row`` first so it sorts next to the input.
REPORT_COLUMNS: Final[tuple[str, ...]] = (
    "Severity",
    "Row",
    "ELEMENT ID",
    "ELEMENT-TYPE",
    "Field",
    "Value",
    "Problem",
    "Expected",
    "Action",
)

#: Suffixes that produce a spreadsheet-friendly report instead of a text log.
CSV_SUFFIXES: Final[frozenset[str]] = frozenset({".csv"})

#: BOM encoding, so umlauts survive a double-click into Excel.
REPORT_CSV_ENCODING: Final = "utf-8-sig"


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


#: A finding together with the severity it was reported at.
ReportedIssue = tuple[str, "Issue"]


def sortIssues(issues: list[ReportedIssue]) -> list[ReportedIssue]:
    """Order findings by Excel row so the report can be worked top to bottom.

    Errors come before warnings for the same row, and findings without a row
    (schema-level problems) go last because they are not tied to a cell.
    """
    severityOrder = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1}
    return sorted(
        issues,
        key=lambda entry: (
            entry[1].row is None,
            entry[1].row or 0,
            severityOrder.get(entry[0], 9),
        ),
    )


def issueRow(severity: str, issue: Issue) -> list[str]:
    """Flatten a finding into one report row, in :data:`REPORT_COLUMNS` order."""
    return [
        severity,
        "" if issue.row is None else str(issue.row),
        issue.elementId,
        issue.elementType,
        issue.field,
        "" if issue.value is None and not issue.field else formatValue(issue.value),
        issue.problem,
        issue.expected,
        issue.action,
    ]


def writeIssueReport(
    issues: list[ReportedIssue],
    path: Path,
    logger: logging.Logger,
) -> Path:
    """Write every finding of the run to ``path`` so it can be worked through.

    A ``.csv`` target produces a spreadsheet the user can open next to the input
    workbook and sort by ``Row``; any other suffix produces the same readable
    blocks as the console. The file is always written - including for the run
    that aborted, which is exactly the run whose errors need fixing.

    Returns:
        The absolute path of the written report.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sortIssues(issues)

    if path.suffix.lower() in CSV_SUFFIXES:
        with path.open("w", encoding=REPORT_CSV_ENCODING, newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(REPORT_COLUMNS)
            writer.writerows(issueRow(severity, issue) for severity, issue in ordered)
    else:
        blocks = [
            issue.render(f"{severity} {index}/{len(ordered)}")
            for index, (severity, issue) in enumerate(ordered, start=1)
        ]
        header = f"{len(ordered)} finding(s) - errors must be fixed before a rerun succeeds.\n"
        path.write_text(
            header + "\n" + "\n\n".join(blocks) + ("\n" if blocks else ""),
            encoding="utf-8",
        )

    errorCount = sum(1 for severity, _ in ordered if severity == SEVERITY_ERROR)
    logger.info(
        "Wrote issue report with %d error(s) and %d warning(s) to: %s",
        errorCount,
        len(ordered) - errorCount,
        path.resolve(),
    )
    return path.resolve()


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
    strict: bool = False

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

    def allIssues(self) -> list[ReportedIssue]:
        """Every finding with its severity, errors first, then by Excel row."""
        combined = [(SEVERITY_ERROR, issue) for issue in self.errors]
        combined += [(SEVERITY_WARNING, issue) for issue in self.warnings]
        return sortIssues(combined)

    def abortIfFailed(self, phase: str) -> None:
        """Abort the conversion when this phase produced any error.

        Only in ``strict`` mode. By default the errors have already been logged
        in full and the conversion carries on, so the CSV files still get
        written and the log is the list of things to fix.
        """
        if not self.errors or not self.strict:
            return
        count = len(self.errors)
        self.logger.critical(
            "Conversion aborted in phase '%s': %d fatal error%s. No CSV files were written.",
            phase,
            count,
            "" if count == 1 else "s",
            stacklevel=2,
        )
        raise ConversionError(
            f"{count} fatal error(s) during phase '{phase}'",
            issues=list(self.allIssues()),
        )
