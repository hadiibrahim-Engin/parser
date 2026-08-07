"""Discovery of the documents that make up a CGMES export.

A real export arrives as loose files, a directory, or a zip archive. All three
are reduced to the same :class:`DocumentSource`, so nothing downstream cares
where a profile physically lives.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from cgmes2excel.cgmes.reader import DocumentStats, RawObject, readRdfXmlStream

_XML_SUFFIX = ".xml"
_ZIP_SUFFIX = ".zip"


class InputNotFoundError(FileNotFoundError):
    """Raised when a requested input path does not exist."""


@dataclass(frozen=True, slots=True)
class DocumentSource:
    """One CGMES document, whether a file on disk or a member of an archive."""

    container: Path
    member: str | None = None

    @property
    def name(self) -> str:
        return Path(self.member).name if self.member else self.container.name

    @property
    def displayPath(self) -> Path:
        """A path that identifies the document, including its archive if any."""
        return self.container / self.member if self.member else self.container

    def open(self) -> BinaryIO:
        if self.member is None:
            return open(self.container, "rb")
        archive = zipfile.ZipFile(self.container)
        return _ClosingMember(archive, archive.open(self.member))  # type: ignore[return-value]

    def __str__(self) -> str:
        return str(self.displayPath)


class _ClosingMember:
    """A zip member stream that closes its archive with it."""

    def __init__(self, archive: zipfile.ZipFile, stream: BinaryIO) -> None:
        self._archive = archive
        self._stream = stream

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def close(self) -> None:
        self._stream.close()
        self._archive.close()

    def __enter__(self) -> _ClosingMember:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def discoverDocuments(paths: list[Path]) -> list[DocumentSource]:
    """Expand files, directories and archives into the documents they contain."""
    sources: list[DocumentSource] = []
    seen: set[tuple[Path, str | None]] = set()
    for path in paths:
        if not path.exists():
            raise InputNotFoundError(f"Input path does not exist: {path}")
        for source in _expand(path):
            key = (source.container.resolve(), source.member)
            if key not in seen:
                seen.add(key)
                sources.append(source)
    return sources


def _expand(path: Path) -> Iterator[DocumentSource]:
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file():
                yield from _expandFile(child)
        return
    yield from _expandFile(path)


def _expandFile(path: Path) -> Iterator[DocumentSource]:
    suffix = path.suffix.lower()
    if suffix == _ZIP_SUFFIX:
        with zipfile.ZipFile(path) as archive:
            members = sorted(
                info.filename
                for info in archive.infolist()
                if not info.is_dir() and info.filename.lower().endswith(_XML_SUFFIX)
            )
        for member in members:
            yield DocumentSource(container=path, member=member)
    elif suffix == _XML_SUFFIX:
        yield DocumentSource(container=path)


def readDocument(source: DocumentSource, stats: DocumentStats | None = None) -> Iterator[RawObject]:
    """Stream the RDF descriptions of one document source."""
    stream = source.open()
    try:
        yield from readRdfXmlStream(stream, source.displayPath, stats)
    finally:
        stream.close()
