"""A derived value together with the traversal that produced it.

Every non-trivial derivation returns one of these so that a debug session can
answer "why does this cell say Umspannwerk Beta?" without re-deriving anything.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Resolution[T]:
    """The outcome of one derivation: a value, or a reason there is none."""

    value: T | None
    trace: tuple[str, ...] = ()
    reason: str | None = None

    @classmethod
    def of(cls, value: T, *steps: str) -> Resolution[T]:
        return cls(value=value, trace=tuple(steps))

    @classmethod
    def empty(cls, reason: str, *steps: str) -> Resolution[T]:
        return cls(value=None, trace=tuple(steps), reason=reason)

    @property
    def found(self) -> bool:
        return self.value is not None

    def then(self, *steps: str) -> Resolution[T]:
        return Resolution(value=self.value, trace=self.trace + tuple(steps), reason=self.reason)

    def withValue[U](self, value: U, *steps: str) -> Resolution[U]:
        return Resolution(value=value, trace=self.trace + tuple(steps))

    def describe(self) -> str:
        path = " -> ".join(self.trace)
        if self.found:
            return path
        return f"{path} -> unavailable ({self.reason})" if path else f"unavailable ({self.reason})"

    def __bool__(self) -> bool:
        return self.found


EMPTY: Resolution[object] = Resolution(value=None, reason="notAttempted")
