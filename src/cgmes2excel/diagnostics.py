"""Collection and reporting of data-quality findings.

Every derivation step reports what it could not do here instead of failing
silently. Findings are both logged (rate-limited, so one systemic problem cannot
flood the console) and retained in full for the run summary.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum

from cgmes2excel.logging import getLogger


class Severity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


_LOG_LEVELS = {
    Severity.INFO: logging.INFO,
    Severity.WARNING: logging.WARNING,
    Severity.ERROR: logging.ERROR,
}


@dataclass(frozen=True)
class Issue:
    """One data-quality finding, with enough context to investigate it."""

    code: str
    severity: Severity
    message: str
    context: dict[str, str] = field(default_factory=dict)

    def render(self) -> str:
        if not self.context:
            return self.message
        details = " ".join(f"{key}={value}" for key, value in self.context.items())
        return f"{self.message} ({details})"


class Diagnostics:
    """Aggregates issues and empty-field reasons for one conversion run."""

    def __init__(self, logger: logging.Logger | None = None, maxLoggedPerCode: int = 10) -> None:
        self.logger = logger if logger is not None else getLogger("cgmes2excel.diagnostics")
        self.maxLoggedPerCode = maxLoggedPerCode
        self.issues: list[Issue] = []
        self._logged: Counter[str] = Counter()
        self._emptyFields: dict[str, Counter[str]] = defaultdict(Counter)
        self._emptyReasons: dict[tuple[str, str], str] = {}

    # -- reporting ------------------------------------------------------------

    def report(self, code: str, severity: Severity, message: str, **context: object) -> Issue:
        issue = Issue(
            code=code,
            severity=severity,
            message=message,
            context={key: str(value) for key, value in context.items()},
        )
        self.issues.append(issue)
        self._maybeLog(issue)
        return issue

    def info(self, code: str, message: str, **context: object) -> Issue:
        return self.report(code, Severity.INFO, message, **context)

    def warn(self, code: str, message: str, **context: object) -> Issue:
        return self.report(code, Severity.WARNING, message, **context)

    def error(self, code: str, message: str, **context: object) -> Issue:
        return self.report(code, Severity.ERROR, message, **context)

    def _maybeLog(self, issue: Issue) -> None:
        seen = self._logged[issue.code]
        self._logged[issue.code] = seen + 1
        if seen < self.maxLoggedPerCode:
            self.logger.log(_LOG_LEVELS[issue.severity], issue.render())

    def logSuppressionSummary(self) -> None:
        """Report how many findings were withheld from the console per code."""
        for code, total in sorted(self._logged.items()):
            hidden = total - self.maxLoggedPerCode
            if hidden > 0:
                self.logger.info("%s: %d further occurrence(s) not shown", code, hidden)

    # -- empty output fields --------------------------------------------------

    def noteEmptyField(self, sheet: str, column: str, reason: str) -> None:
        """Record that ``column`` stayed empty for one row, and why."""
        self._emptyFields[sheet][column] += 1
        self._emptyReasons.setdefault((sheet, column), reason)

    def emptyFieldsBySheet(self) -> dict[str, dict[str, int]]:
        return {sheet: dict(columns) for sheet, columns in self._emptyFields.items()}

    def emptyFieldReason(self, sheet: str, column: str) -> str | None:
        return self._emptyReasons.get((sheet, column))

    @property
    def emptyFieldCount(self) -> int:
        return sum(sum(columns.values()) for columns in self._emptyFields.values())

    # -- aggregates -----------------------------------------------------------

    def countByCode(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for issue in self.issues:
            counts[issue.code] += 1
        return dict(counts)

    def countBySeverity(self, severity: Severity) -> int:
        return sum(1 for issue in self.issues if issue.severity is severity)

    @property
    def warningCount(self) -> int:
        return self.countBySeverity(Severity.WARNING)

    @property
    def errorCount(self) -> int:
        return self.countBySeverity(Severity.ERROR)

    @property
    def unresolvedReferenceCount(self) -> int:
        return sum(1 for issue in self.issues if issue.code == "unresolvedReference")
