"""Filesystem-level validation of the four selected paths.

Scope note: these checks answer "can this path be used at all", not "is this a
valid CGMES export". Nothing here parses a file or knows what CGMES is. Domain
validation is added later through ``extraCheckers`` without touching the user
interface.

The whole module is pure: it reads the filesystem and returns a report, and has
no other effect.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.states import ORDERED_ROLES, CheckStatus, InputRole

ZIP_SUFFIX = ".zip"

ExtraChecker = Callable[[ConversionRequest], Iterable["InputCheck"]]


@dataclass(frozen=True, slots=True)
class InputCheck:
    """The verdict on one selected path."""

    role: InputRole
    status: CheckStatus
    message: str

    @property
    def isBlocking(self) -> bool:
        return self.status is CheckStatus.ERROR


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """The verdict on a whole request."""

    checks: tuple[InputCheck, ...] = ()

    @property
    def isValid(self) -> bool:
        """Whether a conversion may start. Warnings do not block; errors do."""
        return not any(check.isBlocking for check in self.checks)

    @property
    def errorCount(self) -> int:
        return sum(1 for check in self.checks if check.status is CheckStatus.ERROR)

    @property
    def warningCount(self) -> int:
        return sum(1 for check in self.checks if check.status is CheckStatus.WARNING)

    @property
    def summary(self) -> str:
        if self.isValid:
            return "Inputs validated"
        if self.errorCount == 1:
            return "1 problem found"
        return f"{self.errorCount} problems found"

    def checkFor(self, role: InputRole) -> InputCheck | None:
        for check in self.checks:
            if check.role is role:
                return check
        return None


def validateRequest(
    request: ConversionRequest,
    extraCheckers: Sequence[ExtraChecker] = (),
) -> ValidationReport:
    """Check every selected path and report what stands in the way.

    ``extraCheckers`` is the seam for domain-specific validation: each callable
    receives the request and yields additional checks, which are appended in the
    order given.
    """
    checks: list[InputCheck] = [
        _checkProfileZip(request.pathFor(InputRole.PROFILE_ZIP)),
        _checkDataset(InputRole.SNAPSHOT_DATASET, request.pathFor(InputRole.SNAPSHOT_DATASET)),
        _checkDataset(InputRole.CIM_CACHE_DATASET, request.pathFor(InputRole.CIM_CACHE_DATASET)),
        _checkOutputDirectory(request.pathFor(InputRole.OUTPUT_DIRECTORY)),
    ]
    for checker in extraCheckers:
        checks.extend(checker(request))
    return ValidationReport(checks=tuple(checks))


def emptyReport() -> ValidationReport:
    """A report with no checks, used before the user has validated anything."""
    return ValidationReport()


def _notSelected(role: InputRole) -> InputCheck:
    return InputCheck(role=role, status=CheckStatus.ERROR, message="Not selected")


def _checkProfileZip(path: Path | None) -> InputCheck:
    role = InputRole.PROFILE_ZIP
    if path is None:
        return _notSelected(role)
    if not path.exists():
        return _error(role, "File does not exist")
    if not path.is_file():
        return _error(role, "Not a file")
    if path.suffix.lower() != ZIP_SUFFIX:
        return _error(role, "Not a .zip archive")
    if not _isReadable(path):
        return _error(role, "File is not readable")
    if _sizeOf(path) == 0:
        return _error(role, "File is empty")
    return _ok(role)


def _checkDataset(role: InputRole, path: Path | None) -> InputCheck:
    """A dataset may be a directory of documents or a single file."""
    if path is None:
        return _notSelected(role)
    if not path.exists():
        return _error(role, "Path does not exist")
    if not _isReadable(path):
        return _error(role, "Path is not readable")
    if path.is_dir() and _isEmptyDirectory(path):
        return InputCheck(role=role, status=CheckStatus.WARNING, message="Directory is empty")
    return _ok(role)


def _checkOutputDirectory(path: Path | None) -> InputCheck:
    """An existing output directory is a warning, not an error.

    It is usable, but previous output in it may be overwritten, and that is
    worth surfacing before a run rather than after one.
    """
    role = InputRole.OUTPUT_DIRECTORY
    if path is None:
        return _notSelected(role)
    if path.exists():
        if not path.is_dir():
            return _error(role, "Not a directory")
        if not _isWritable(path):
            return _error(role, "Directory is not writable")
        return InputCheck(role=role, status=CheckStatus.WARNING, message="Directory exists")

    parent = path.parent
    if not parent.exists():
        return _error(role, "Parent directory does not exist")
    if not _isWritable(parent):
        return _error(role, "Parent directory is not writable")
    return InputCheck(role=role, status=CheckStatus.WARNING, message="Will be created")


def _ok(role: InputRole) -> InputCheck:
    return InputCheck(role=role, status=CheckStatus.OK, message="OK")


def _error(role: InputRole, message: str) -> InputCheck:
    return InputCheck(role=role, status=CheckStatus.ERROR, message=message)


def _isReadable(path: Path) -> bool:
    return os.access(path, os.R_OK)


def _isWritable(path: Path) -> bool:
    return os.access(path, os.W_OK)


def _isEmptyDirectory(path: Path) -> bool:
    try:
        return not any(path.iterdir())
    except OSError:
        # Unreadable directories are reported by the readability check; treating
        # one as non-empty here avoids a misleading second complaint.
        return False


def _sizeOf(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


__all__ = [
    "ORDERED_ROLES",
    "ExtraChecker",
    "InputCheck",
    "ValidationReport",
    "emptyReport",
    "validateRequest",
]
