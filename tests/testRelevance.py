"""Tests for the dynamic ``relevant für`` logic (cases 19-21)."""

from __future__ import annotations

import logging

from conftest import RecordingHandler, convertRows, elementRow, stationRow

from excelToCsv.loggingSetup import getLogger
from excelToCsv.relevance import extractRelevanceColumns, extractRelevanceLabel

RELEVANCE_50HERTZ = "Interesting/Relevant for (50Hertz)"
RELEVANCE_AMPRION = "Interesting/Relevant for (Amprion)"
RELEVANCE_TENNET = "Interesting/Relevant for (TennetD)"


def testRelevantForFromZeroAndOne(logger: logging.Logger) -> None:
    """Case 19: 0/1 as the boolean source."""
    row = stationRow(
        **{RELEVANCE_50HERTZ: 1, RELEVANCE_AMPRION: 0, RELEVANCE_TENNET: 1}
    )
    result = convertRows([row], logger)
    assert result.stations.iloc[0]["relevant für"] == "50Hertz;TennetD"


def testRelevantForFromTrueAndFalse(logger: logging.Logger) -> None:
    """Case 20: True/False as the boolean source."""
    row = stationRow(
        **{RELEVANCE_50HERTZ: "True", RELEVANCE_AMPRION: "false", RELEVANCE_TENNET: True}
    )
    result = convertRows([row], logger)
    assert result.stations.iloc[0]["relevant für"] == "50Hertz;TennetD"


def testUnknownBooleanValueOnlyWarns(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """Case 21: an unknown boolean value -> warning, not TRUE."""
    row = stationRow(**{RELEVANCE_50HERTZ: "maybe", RELEVANCE_AMPRION: 1})
    result = convertRows([row], logger)

    assert result.stations.iloc[0]["relevant für"] == "Amprion"
    warnings = logCapture.text(logging.WARNING)
    assert "Unrecognized boolean value - not interpreted as TRUE." in warnings
    assert "Value: maybe" in warnings
    assert f"Field: {RELEVANCE_50HERTZ}" in warnings


def testEmptyRelevanceProducesAnEmptyField(logger: logging.Logger) -> None:
    row = stationRow(**{RELEVANCE_50HERTZ: "", RELEVANCE_AMPRION: 0})
    result = convertRows([row], logger)
    assert result.stations.iloc[0]["relevant für"] == ""


def testRelevanceAppliesToNetworkElementsToo(logger: logging.Logger) -> None:
    rows = [
        stationRow(**{RELEVANCE_50HERTZ: 0}),
        stationRow(**{"ELEMENT ID": "Hamburg_380", "Latitude": "53.5", "Longitude": "9.9",
                      RELEVANCE_50HERTZ: 0}),
        elementRow(**{RELEVANCE_50HERTZ: 1}),
    ]
    result = convertRows(rows, logger)
    assert result.networkElements.iloc[0]["relevant für"] == "50Hertz"
    assert result.stations.iloc[0]["relevant für"] == ""


def testWithoutRelevanceColumnsFieldStaysEmpty(logger: logging.Logger) -> None:
    result = convertRows([stationRow()], logger)
    assert result.stations.iloc[0]["relevant für"] == ""


def testIgnoredColumnsAreNotTreatedAsRelevance() -> None:
    """``OPC INTERESTING ASSET`` must not count as a relevance column."""
    columns = [
        "OPC INTERESTING ASSET",
        "OPC Map only",
        "interconnector relevant for something",
        RELEVANCE_50HERTZ,
    ]
    detected = extractRelevanceColumns(columns, getLogger("test"))
    assert [item.column for item in detected] == [RELEVANCE_50HERTZ]
    assert [item.label for item in detected] == ["50Hertz"]


def testLabelExtractionFallsBackToKeywordStripping() -> None:
    assert extractRelevanceLabel("Interesting/Relevant for (APG)") == "APG"
    assert extractRelevanceLabel("Relevant for TennetD") == "TennetD"
    assert extractRelevanceLabel("Interesting / Relevant for: 50Hertz") == "50Hertz"


# --------------------------------------------------------------------------- #
# Semicolon format
# --------------------------------------------------------------------------- #


def testSeveralOrganisationsAreJoinedBySemicolon(logger: logging.Logger) -> None:
    """Three hits become one field, separated by semicolons, in column order."""
    row = stationRow(**{RELEVANCE_50HERTZ: 1, RELEVANCE_AMPRION: 1, RELEVANCE_TENNET: 1})
    result = convertRows([row], logger)

    value = result.stations.iloc[0]["relevant für"]
    assert value == "50Hertz;Amprion;TennetD"
    assert value.split(";") == ["50Hertz", "Amprion", "TennetD"]


def testSingleOrganisationHasNoSeparator(logger: logging.Logger) -> None:
    row = stationRow(**{RELEVANCE_50HERTZ: 0, RELEVANCE_AMPRION: 1, RELEVANCE_TENNET: 0})
    assert convertRows([row], logger).stations.iloc[0]["relevant für"] == "Amprion"


def testRelevanceNeedsNoCsvQuoting(tmp_path, logger: logging.Logger) -> None:
    """A semicolon needs no quoting in a comma-separated file."""
    import csv

    from excelToCsv.writer import writeCsvFiles

    row = stationRow(**{RELEVANCE_50HERTZ: 1, RELEVANCE_TENNET: 1})
    result = convertRows([row], logger)
    writeCsvFiles(result.stations, result.networkElements, tmp_path, logger)

    text = (tmp_path / "Stationen.csv").read_text(encoding="utf-8")
    assert "50Hertz;TennetD" in text
    assert '"50Hertz;TennetD"' not in text

    with (tmp_path / "Stationen.csv").open(encoding="utf-8", newline="") as handle:
        record = next(iter(csv.DictReader(handle)))
    assert record["relevant für"] == "50Hertz;TennetD"


def testJoinRelevanceHandlesEveryCount() -> None:
    from excelToCsv.relevance import joinRelevance

    assert joinRelevance([]) == ""
    assert joinRelevance(["APG"]) == "APG"
    assert joinRelevance(["APG", "TennetD", "50Hertz"]) == "APG;TennetD;50Hertz"
