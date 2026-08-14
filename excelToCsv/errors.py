"""Exception types of the converter.

The split:

* :class:`ConversionError` ends the conversion (fatal, exit code != 0).
* :class:`NormalizationError` is a *local* failure of a normalization function.
  The caller collects it and turns it into a detailed message
  (row / ELEMENT ID / field / value).
"""

from __future__ import annotations


class ConversionError(Exception):
    """Fatal error: the conversion is aborted and no CSV files are produced."""


class NormalizationError(ValueError):
    """A single value could not be normalized reliably.

    Carries the business description (``problem``) and the expected state
    (``expected``) so the caller can build a complete message without needing to
    know the context again.
    """

    def __init__(self, problem: str, expected: str = "") -> None:
        super().__init__(problem)
        self.problem = problem
        self.expected = expected
