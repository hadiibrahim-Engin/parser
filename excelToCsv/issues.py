"""Einsammeln und Formatieren von fachlichen Befunden (Errors / Warnings).

Zentrale Fehlerstrategie:

* ``WARNING`` – fachlich tolerierbar, die Conversion läuft weiter.
* ``ERROR``   – IMMER fatal. Es werden alle Fehler einer Phase eingesammelt und
  vollständig geloggt, danach bricht die Conversion ab, BEVOR irgendeine
  CSV-Datei entsteht.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from excelToCsv.errors import ConversionError

#: Darstellung eines leeren Wertes in Log-Meldungen.
EMPTY_DISPLAY = "<empty>"


def formatValue(value: object) -> str:
    """Stellt einen Zellwert für Log-Ausgaben dar; leere Werte als ``<empty>``."""
    if value is None:
        return EMPTY_DISPLAY
    text = str(value).strip()
    return text if text else EMPTY_DISPLAY


@dataclass(frozen=True, slots=True)
class Issue:
    """Ein einzelner Befund mit vollem Kontext zur Rückverfolgung ins Excel."""

    problem: str
    row: int | None = None
    elementId: str = ""
    elementType: str = ""
    field: str = ""
    value: object = None
    expected: str = ""
    action: str = ""

    def render(self, headline: str) -> str:
        """Baut den mehrzeiligen Log-Block dieses Befundes."""
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
    """Sammelt Fehler und Warnungen und erzwingt den Abbruch an Phasengrenzen.

    Fehler werden sofort geloggt (damit der Anwender sie live sieht), aber erst
    an einer definierten Phasengrenze via :meth:`abortIfFailed` in einen
    :class:`ConversionError` überführt. So sieht der Anwender in einem Lauf
    ALLE Probleme statt nur des ersten.
    """

    logger: logging.Logger
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    maxLoggedErrors: int = 200

    def error(self, problem: str, **context: object) -> None:
        """Erfasst einen fatalen Befund und loggt ihn sofort.

        ``stacklevel=2`` sorgt dafür, dass die Quellenangabe im Log auf das
        aufrufende Fachmodul zeigt (z. B. ``stations.py``) statt auf diese Datei.
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
        """Erfasst einen tolerierbaren Befund und loggt ihn sofort."""
        issue = Issue(problem=problem, **context)  # type: ignore[arg-type]
        self.warnings.append(issue)
        self.logger.warning(issue.render("Tolerable issue."), stacklevel=2)

    @property
    def failed(self) -> bool:
        """``True``, sobald mindestens ein fataler Fehler erfasst wurde."""
        return bool(self.errors)

    def abortIfFailed(self, phase: str) -> None:
        """Bricht die Conversion ab, wenn in dieser Phase Fehler auftraten."""
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
