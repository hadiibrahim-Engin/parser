"""The request value, preferences clamping, session capture and version pinning."""

from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path

import pytest

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.result import ConversionOutcome, LogRecord
from cgmesparser.gui.core.session import SessionInfo
from cgmesparser.gui.core.settings import (
    DEFAULT_LOG_ROWS,
    MAX_LOG_ROWS,
    MIN_LOG_ROWS,
    Preferences,
)
from cgmesparser.gui.core.states import ORDERED_STAGES, InputRole, MessageLevel, ProcessingStage
from cgmesparser.gui.version import __version__


class TestConversionRequest:
    def testStartsEmptyAndIncomplete(self) -> None:
        request = ConversionRequest()
        assert request.isComplete is False
        assert all(request.pathFor(role) is None for role in InputRole)

    def testWithPathDoesNotMutateTheOriginal(self, tmp_path: Path) -> None:
        original = ConversionRequest()
        updated = original.withPath(InputRole.PROFILE_ZIP, tmp_path / "a.zip")
        assert original.profileZip is None
        assert updated.profileZip == tmp_path / "a.zip"

    def testEveryRoleRoundTrips(self, tmp_path: Path) -> None:
        request = ConversionRequest()
        for role in InputRole:
            request = request.withPath(role, tmp_path / role.name)
        assert request.isComplete is True
        for role in InputRole:
            assert request.pathFor(role) == tmp_path / role.name

    def testARoleCanBeCleared(self, tmp_path: Path) -> None:
        request = ConversionRequest().withPath(InputRole.PROFILE_ZIP, tmp_path / "a.zip")
        assert request.withPath(InputRole.PROFILE_ZIP, None).profileZip is None

    def testTwoEqualRequestsCompareEqual(self, tmp_path: Path) -> None:
        one = ConversionRequest(profileZip=tmp_path / "a.zip")
        other = ConversionRequest(profileZip=tmp_path / "a.zip")
        assert one == other


class TestPreferences:
    def testDefaultsAreSensible(self) -> None:
        preferences = Preferences()
        assert preferences.rememberPaths is True
        assert preferences.maxLogRows == DEFAULT_LOG_ROWS

    @pytest.mark.parametrize(
        ("given", "expected"),
        [(0, MIN_LOG_ROWS), (5, MIN_LOG_ROWS), (10**9, MAX_LOG_ROWS), (2500, 2500)],
    )
    def testLogRowsAreClamped(self, given: int, expected: int) -> None:
        assert Preferences(maxLogRows=given).normalised().maxLogRows == expected

    def testUnparseableLogRowsFallBackToTheDefault(self) -> None:
        assert Preferences(maxLogRows="many").normalised().maxLogRows == DEFAULT_LOG_ROWS


class TestSessionInfo:
    def testSessionIdIsDerivedFromTheGivenMoment(self) -> None:
        info = SessionInfo.capture("6.7.2", datetime(2025, 5, 13, 8, 14))
        assert info.sessionId == "2025-05-13_0814"

    def testEveryFieldIsPopulated(self) -> None:
        info = SessionInfo.capture("6.7.2")
        assert info.pysideVersion == "6.7.2"
        assert info.pythonVersion.count(".") == 2
        assert info.user
        assert info.computer

    def testAnUnknownPysideVersionIsNamedNotBlank(self) -> None:
        assert SessionInfo.capture("").pysideVersion == "unknown"


class TestStages:
    def testSixStagesInDisplayOrder(self) -> None:
        assert len(ORDERED_STAGES) == 6
        assert ORDERED_STAGES[0] is ProcessingStage.LOAD_MODELS
        assert ORDERED_STAGES[-1] is ProcessingStage.EXCEL_EXPORT

    def testPositionsAreContiguous(self) -> None:
        assert [stage.position for stage in ORDERED_STAGES] == list(range(6))

    def testLabelsAreHumanReadable(self) -> None:
        assert ProcessingStage.CLASSIFY_SUBSTATIONS.label == "Classify Substations"


class TestLogRecord:
    def testClockTimeIsHoursMinutesSeconds(self) -> None:
        record = LogRecord(datetime(2025, 5, 13, 8, 14, 22), MessageLevel.INFO, "started")
        assert record.clockTime == "08:14:22"

    def testNowStampsTheCurrentTime(self) -> None:
        assert LogRecord.now(MessageLevel.ERROR, "boom").level is MessageLevel.ERROR


class TestOutcome:
    def testOutcomeCarriesTheCountsTheOutputCardShows(self, tmp_path: Path) -> None:
        outcome = ConversionOutcome(tmp_path, 3, 1284, 146, datetime.now())
        assert (outcome.excelFileCount, outcome.detectedLines, outcome.detectedSubstations) == (
            3,
            1284,
            146,
        )


class TestVersion:
    def testVersionMatchesPyproject(self) -> None:
        """version.py is the source of truth; the two must never drift apart."""
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
        assert declared == __version__
