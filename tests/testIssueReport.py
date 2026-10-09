"""Tests for the issue report written via ``--issue-file``."""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import conftest
import pytest
from conftest import elementRow, stationRow, writeExcel

from excelToCsv.cli import EXIT_CONVERSION_ERROR, EXIT_SUCCESS, failureIssues, main
from excelToCsv.errors import ConversionError
from excelToCsv.issues import (
    REPORT_COLUMNS,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    Issue,
    sortIssues,
    writeIssueReport,
)
from excelToCsv.schema import STATIONS_FILENAME

RELEVANCE = "Interesting/Relevant for (50Hertz)"


def readReport(path: Path) -> list[dict[str, str]]:
    """Read the CSV report back the way Excel would."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def brokenRows() -> list[dict[str, object]]:
    """One warning (station id convention) and one fatal error (dangling reference)."""
    return [
        stationRow(**{"ELEMENT ID": "Berlin", RELEVANCE: "R"}),
        elementRow(**{"Station 1": "Berlin", "Station 2": "GibtsNicht_380"}),
    ]


# --------------------------------------------------------------------------- #
# The report exists for exactly the run that failed
# --------------------------------------------------------------------------- #


def testReportIsWrittenEvenWhenTheConversionAborts(tmp_path: Path) -> None:
    inputFile = writeExcel(brokenRows(), tmp_path / "input.xlsx")
    report = tmp_path / "issues.csv"

    exitCode = main(
        [
            str(inputFile),
            "--output-dir",
            str(tmp_path / "out"),
            "--issue-file",
            str(report),
            "--strict",
            "--no-color",
        ]
    )

    assert exitCode == EXIT_CONVERSION_ERROR
    assert report.is_file(), "the failing run is the one whose report matters"
    assert not (tmp_path / "out" / STATIONS_FILENAME).exists()

    records = readReport(report)
    assert any(record["Severity"] == SEVERITY_ERROR for record in records)
    assert any(record["Severity"] == SEVERITY_WARNING for record in records)


def testReportCarriesTheFullRowContext(tmp_path: Path) -> None:
    inputFile = writeExcel(brokenRows(), tmp_path / "input.xlsx")
    report = tmp_path / "issues.csv"
    main([str(inputFile), "-o", str(tmp_path / "out"), "--issue-file", str(report), "--strict", "--no-color"])

    errors = [record for record in readReport(report) if record["Severity"] == SEVERITY_ERROR]
    assert len(errors) == 1
    finding = errors[0]
    assert finding["Row"] == "3"
    assert finding["ELEMENT ID"] == "LINE_471"
    assert finding["ELEMENT-TYPE"] == "LINE"
    assert finding["Field"] == "Station 2"
    assert finding["Value"] == "GibtsNicht_380"
    assert "does not match any station" in finding["Problem"]
    assert finding["Expected"]


def testSuccessfulRunReportsItsWarnings(tmp_path: Path) -> None:
    rows = [stationRow(**{"ELEMENT ID": "Berlin"})]
    inputFile = writeExcel(rows, tmp_path / "input.xlsx")
    report = tmp_path / "issues.csv"

    exitCode = main(
        [str(inputFile), "-o", str(tmp_path / "out"), "--issue-file", str(report), "--legacy", "--no-color"]
    )

    assert exitCode == EXIT_SUCCESS
    records = readReport(report)
    assert [record["Severity"] for record in records] == [SEVERITY_WARNING]
    assert "does not follow the '<name>_<voltage>' convention" in records[0]["Problem"]


def testCleanRunWritesAnEmptyReport(tmp_path: Path) -> None:
    """A header-only report proves the run was checked, rather than skipped."""
    rows = [
        stationRow(),
        stationRow(
            **{
                "ELEMENT ID": "Hamburg_380",
                "Latitude": "53.551086",
                "Longitude": "9.993682",
                "UCTE CODE": "DHAMBRG1",
            }
        ),
        elementRow(),
    ]
    inputFile = writeExcel(rows, tmp_path / "input.xlsx")
    report = tmp_path / "issues.csv"

    assert main([str(inputFile), "-o", str(tmp_path / "out"), "--issue-file", str(report),
                 "--no-color"]) == EXIT_SUCCESS
    assert readReport(report) == []
    assert report.read_text(encoding="utf-8-sig").splitlines()[0] == ",".join(REPORT_COLUMNS)


def testWithoutTheOptionNoReportAppears(tmp_path: Path) -> None:
    inputFile = writeExcel(brokenRows(), tmp_path / "input.xlsx")
    main([str(inputFile), "-o", str(tmp_path / "out"), "--no-color"])
    assert list(tmp_path.glob("*.csv")) == []


# --------------------------------------------------------------------------- #
# Formats and ordering
# --------------------------------------------------------------------------- #


def testCsvReportUsesTheAgreedColumns(tmp_path: Path) -> None:
    report = tmp_path / "issues.csv"
    writeIssueReport(
        [(SEVERITY_ERROR, Issue(problem="boom", row=7, field="Latitude"))],
        report,
        logging.getLogger("test"),
    )
    with report.open(encoding="utf-8-sig", newline="") as handle:
        assert next(csv.reader(handle)) == list(REPORT_COLUMNS)


def testCsvReportKeepsUmlautsReadableForExcel(tmp_path: Path) -> None:
    report = tmp_path / "issues.csv"
    writeIssueReport(
        [(SEVERITY_WARNING, Issue(problem="Umspannwerk Hämburg fehlt", row=2))],
        report,
        logging.getLogger("test"),
    )
    assert report.read_bytes().startswith(b"\xef\xbb\xbf"), "BOM so Excel picks UTF-8"
    assert "Hämburg" in report.read_text(encoding="utf-8-sig")


@pytest.mark.parametrize("suffix", [".log", ".txt"])
def testNonCsvSuffixGetsReadableBlocks(suffix: str, tmp_path: Path) -> None:
    report = tmp_path / f"issues{suffix}"
    writeIssueReport(
        [(SEVERITY_ERROR, Issue(problem="boom", row=7, elementId="LINE_1", field="Station 2"))],
        report,
        logging.getLogger("test"),
    )

    text = report.read_text(encoding="utf-8")
    assert "1 finding(s)" in text
    assert "ERROR 1/1" in text
    assert "Row: 7" in text
    assert "ELEMENT ID: LINE_1" in text
    assert "Problem: boom" in text


def testFindingsAreSortedByExcelRow() -> None:
    """Sorted by row, errors before warnings, row-less findings last."""
    unsorted = [
        (SEVERITY_WARNING, Issue(problem="w9", row=9)),
        (SEVERITY_ERROR, Issue(problem="schema")),
        (SEVERITY_WARNING, Issue(problem="w2", row=2)),
        (SEVERITY_ERROR, Issue(problem="e9", row=9)),
        (SEVERITY_ERROR, Issue(problem="e2", row=2)),
    ]
    assert [issue.problem for _, issue in sortIssues(unsorted)] == [
        "e2",
        "w2",
        "e9",
        "w9",
        "schema",
    ]


def testReportDirectoryIsCreated(tmp_path: Path) -> None:
    report = tmp_path / "nested" / "dir" / "issues.csv"
    writeIssueReport([], report, logging.getLogger("test"))
    assert report.is_file()


# --------------------------------------------------------------------------- #
# Failures raised outside the collector
# --------------------------------------------------------------------------- #


def testSchemaFailureStillProducesAnEntry(tmp_path: Path) -> None:
    """A missing input column has no per-row finding - report the message itself."""
    import pandas as pd

    inputFile = tmp_path / "input.xlsx"
    pd.DataFrame([{"TSO": "Amprion", "ELEMENT ID": "Berlin_380"}]).to_excel(
        inputFile, index=False, engine="openpyxl"
    )
    report = tmp_path / "issues.csv"

    assert main([str(inputFile), "-o", str(tmp_path / "out"), "--issue-file", str(report),
                 "--no-color"]) == EXIT_CONVERSION_ERROR

    records = readReport(report)
    assert len(records) == 1
    assert records[0]["Severity"] == SEVERITY_ERROR
    assert "Missing required input column" in records[0]["Problem"]
    assert records[0]["Row"] == ""


def testFailureIssuesPrefersStructuredFindings() -> None:
    structured = [(SEVERITY_ERROR, Issue(problem="detailed", row=5))]
    assert failureIssues(ConversionError("summary", issues=list(structured))) == structured
    assert failureIssues(ConversionError("bare"))[0][1].problem == "bare"


def testUnwritableReportDoesNotMaskTheExitCode(tmp_path: Path) -> None:
    """A broken report path must not turn a conversion failure into a crash."""
    inputFile = writeExcel(brokenRows(), tmp_path / "input.xlsx")
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")

    exitCode = main(
        [
            str(inputFile),
            "-o",
            str(tmp_path / "out"),
            "--issue-file",
            str(blocker / "issues.csv"),
            "--no-color",
        ]
    )
    assert exitCode == EXIT_CONVERSION_ERROR


def testReportAndDebugFileCanBeCombined(tmp_path: Path) -> None:
    inputFile = writeExcel(brokenRows(), tmp_path / "input.xlsx")
    report = tmp_path / "issues.csv"
    debug = tmp_path / "debug.log"

    main(
        [
            str(inputFile),
            "-o",
            str(tmp_path / "out"),
            "--issue-file",
            str(report),
            "--debug-file",
            str(debug),
            "--no-color",
        ]
    )

    assert report.is_file() and debug.is_file()
    assert "DEBUG" in debug.read_text(encoding="utf-8")
    assert len(readReport(report)) >= 1


def testConftestHelperStillBuildsUsableWorkbooks(tmp_path: Path) -> None:
    """Guards the fixture the other tests in this module rely on."""
    assert conftest.writeExcel(brokenRows(), tmp_path / "x.xlsx").is_file()
