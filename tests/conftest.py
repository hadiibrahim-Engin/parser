"""Shared fixtures.

Qt is forced offscreen before PySide6 is imported so the suite runs headless on
a build agent with no display.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402

from cgmesparser.gui.core.request import ConversionRequest  # noqa: E402
from cgmesparser.gui.settingsStore import SettingsStore  # noqa: E402


@pytest.fixture
def settingsStore(tmp_path: Path) -> SettingsStore:
    """A store backed by a temporary ini file, never the real user settings."""
    return SettingsStore(QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))


@pytest.fixture
def validTree(tmp_path: Path) -> dict[str, Path]:
    """A directory layout that passes every filesystem check."""
    profile = tmp_path / "profile.zip"
    profile.write_bytes(b"PK\x05\x06" + b"\x00" * 18)

    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "EQ.xml").write_text("<rdf/>", encoding="utf-8")

    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "cache.xml").write_text("<rdf/>", encoding="utf-8")

    output = tmp_path / "output"
    output.mkdir()

    return {"profile": profile, "snapshot": snapshot, "cache": cache, "output": output}


@pytest.fixture
def validRequest(validTree: dict[str, Path]) -> ConversionRequest:
    return ConversionRequest(
        profileZip=validTree["profile"],
        snapshotDataset=validTree["snapshot"],
        cimCacheDataset=validTree["cache"],
        outputDirectory=validTree["output"],
    )
