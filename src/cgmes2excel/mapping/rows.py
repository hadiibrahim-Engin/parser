"""Field rules and the rows they produce.

A rule is the single documented answer for one output column: where the value
comes from, which fallbacks apply, and what an empty cell means. Rows keep the
derivation of every cell so a value can be explained afterwards.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ..diagnostics import Diagnostics
from ..domain.resolution import Resolution
from .schema import SchemaViolation, SheetSchema, ValueType


@dataclass(frozen=True, slots=True)
class FieldRule[C]:
    """The mapping of one output column."""

    column: str
    description: str
    resolve: Callable[[C], Resolution[object]]

    def apply(self, context: C) -> Resolution[object]:
        return self.resolve(context)


def unavailable[C](column: str, reason: str, description: str) -> FieldRule[C]:
    """A column with no CGMES source: always empty, always for a stated reason."""
    empty: Resolution[object] = Resolution.empty(reason)
    return FieldRule(column=column, description=description, resolve=lambda _context: empty)


@dataclass(slots=True)
class Row:
    """One output row, with the provenance of each cell."""

    sheet: str
    values: list[object | None]
    traces: dict[str, str]
    columns: tuple[str, ...]
    sourceMrid: str = ""

    def value(self, column: str) -> object | None:
        return self.values[self.columns.index(column)]

    def traceOf(self, column: str) -> str:
        return self.traces.get(column, "")


class RowBuilder[C]:
    """Turns a context object into a schema-conformant row."""

    def __init__(self, sheet: SheetSchema, rules: Sequence[FieldRule[C]]) -> None:
        columns = [rule.column for rule in rules]
        if columns != list(sheet.columns):
            raise SchemaViolation(
                f"{sheet.name}: field rules {columns} do not match the contracted columns {list(sheet.columns)}"
            )
        self.sheet = sheet
        self.rules = tuple(rules)

    def build(self, context: C, diagnostics: Diagnostics, sourceMrid: str = "") -> Row:
        values: list[object | None] = []
        traces: dict[str, str] = {}
        for rule in self.rules:
            resolution = rule.apply(context)
            traces[rule.column] = resolution.describe()
            if resolution.found:
                values.append(self._coerce(rule.column, resolution.value))
            else:
                values.append(None)
                diagnostics.noteEmptyField(self.sheet.name, rule.column, resolution.reason or "unknown")
        self.sheet.validateRowWidth(len(values))
        return Row(
            sheet=self.sheet.name,
            values=values,
            traces=traces,
            columns=self.sheet.columns,
            sourceMrid=sourceMrid,
        )

    def _coerce(self, column: str, value: object) -> object:
        """Keep cell types aligned with the schema so identifiers stay text."""
        if self.sheet.valueTypeOf(column) is ValueType.NUMBER:
            return value
        return value if isinstance(value, str) else str(value)


@dataclass(slots=True)
class RuleDocumentation:
    """Human-readable description of the whole mapping, for docs and debugging."""

    sheet: str
    entries: list[tuple[str, str]] = field(default_factory=list)

    @classmethod
    def fromRules(cls, sheet: SheetSchema, rules: Sequence[FieldRule[object]]) -> RuleDocumentation:
        return cls(sheet=sheet.name, entries=[(rule.column, rule.description) for rule in rules])

    def render(self) -> str:
        width = max((len(column) for column, _ in self.entries), default=0)
        lines = [f"{self.sheet}:"]
        lines.extend(f"  {column.ljust(width)}  {description}" for column, description in self.entries)
        return "\n".join(lines)
