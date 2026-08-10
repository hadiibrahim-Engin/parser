"""The four paths that describe one conversion.

The request is immutable. Changing a selection produces a new request rather
than mutating a shared one, so a stale reference can never silently disagree
with what the user sees on screen.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from cgmesparser.gui.core.states import ORDERED_ROLES, InputRole

_FIELD_BY_ROLE: dict[InputRole, str] = {
    InputRole.PROFILE_ZIP: "profileZip",
    InputRole.SNAPSHOT_DATASET: "snapshotDataset",
    InputRole.CIM_CACHE_DATASET: "cimCacheDataset",
    InputRole.OUTPUT_DIRECTORY: "outputDirectory",
}


@dataclass(frozen=True, slots=True)
class ConversionRequest:
    """What the user has selected so far. Any field may still be unset."""

    profileZip: Path | None = None
    snapshotDataset: Path | None = None
    cimCacheDataset: Path | None = None
    outputDirectory: Path | None = None

    def pathFor(self, role: InputRole) -> Path | None:
        return getattr(self, _FIELD_BY_ROLE[role])

    def withPath(self, role: InputRole, path: Path | None) -> ConversionRequest:
        """Return a copy in which ``role`` points at ``path``."""
        return replace(self, **{_FIELD_BY_ROLE[role]: path})

    def paths(self) -> dict[InputRole, Path | None]:
        return {role: self.pathFor(role) for role in ORDERED_ROLES}

    @property
    def isComplete(self) -> bool:
        """Whether all four selections have been made."""
        return all(self.pathFor(role) is not None for role in ORDERED_ROLES)
