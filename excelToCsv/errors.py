"""Exception-Typen des Converters.

Trennung:

* :class:`ConversionError` beendet die Conversion (fatal, Exit-Code != 0).
* :class:`NormalizationError` ist ein *lokaler* Fehler einer Normalisierungs-
  funktion. Er wird vom Aufrufer eingesammelt und in eine detaillierte
  Fehlermeldung (Zeile / ELEMENT ID / Feld / Wert) übersetzt.
"""

from __future__ import annotations


class ConversionError(Exception):
    """Fataler Fehler: die Conversion wird abgebrochen, es entstehen keine CSVs."""


class NormalizationError(ValueError):
    """Ein einzelner Wert konnte nicht zuverlässig normalisiert werden.

    Trägt die fachliche Beschreibung (``problem``) und den erwarteten Zustand
    (``expected``), damit der Aufrufer daraus eine vollständige Fehlermeldung
    bauen kann, ohne den Kontext erneut zu kennen.
    """

    def __init__(self, problem: str, expected: str = "") -> None:
        super().__init__(problem)
        self.problem = problem
        self.expected = expected
