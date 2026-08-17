"""Tests for the log layout: source location, indentation, block separation."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from conftest import RecordingHandler, convertRows, elementRow, stationRow

from excelToCsv.errors import ConversionError
from excelToCsv.loggingSetup import (
    CONTINUATION_INDENT,
    LOGGER_NAME,
    BlockFormatter,
    addDebugFileHandler,
    ansiColorizer,
    buildColorizer,
    plainColorizer,
)


def makeRecord(message: str, level: int = logging.INFO) -> logging.LogRecord:
    """Build a log record the way ``logging`` would create it."""
    return logging.LogRecord(
        name="excelToCsv",
        level=level,
        pathname="/project/excelToCsv/stations.py",
        lineno=42,
        msg=message,
        args=(),
        exc_info=None,
    )


@pytest.fixture()
def formatter() -> BlockFormatter:
    return BlockFormatter(plainColorizer)


def testSingleLineMessageStaysCompact(formatter: BlockFormatter) -> None:
    output = formatter.format(makeRecord("Found 3 station(s)."))

    assert output == "INFO     stations.py:42         Found 3 station(s)."
    assert not output.endswith("\n")


def testLocationShowsSourceFileAndLine(formatter: BlockFormatter) -> None:
    assert "stations.py:42" in formatter.format(makeRecord("irgendwas"))


def testBlockIsIndentedAndSeparated(formatter: BlockFormatter) -> None:
    output = formatter.format(makeRecord("Validation failed.\nRow: 7\nField: Latitude"))

    lines = output.split("\n")
    assert lines[0].startswith("INFO     stations.py:42")
    assert lines[0].endswith("Validation failed.")
    assert lines[1] == f"{CONTINUATION_INDENT}Row: 7"
    assert lines[2] == f"{CONTINUATION_INDENT}Field: Latitude"
    # The trailing blank line sets the block off from what follows.
    assert output.endswith("\n")


def testConsecutiveBlocksGetExactlyOneBlankLine(formatter: BlockFormatter) -> None:
    first = formatter.format(makeRecord("A\ndetail"))
    second = formatter.format(makeRecord("B\ndetail"))

    assert first.endswith("\n")
    assert not second.startswith("\n"), "the predecessor already separated it"


def testBlockAfterSingleLineGetsLeadingBlankLine(formatter: BlockFormatter) -> None:
    formatter.format(makeRecord("Found 3 station(s)."))
    block = formatter.format(makeRecord("Validation failed.\nRow: 7"))

    assert block.startswith("\n")


def testFirstBlockHasNoLeadingBlankLine(formatter: BlockFormatter) -> None:
    assert not formatter.format(makeRecord("Validation failed.\nRow: 7")).startswith("\n")


def testColorizersWrapTheText() -> None:
    colored = ansiColorizer(logging.ERROR, "boom")
    assert colored.startswith("\033[") and colored.endswith("\033[0m")
    assert plainColorizer(logging.ERROR, "boom") == "boom"
    assert buildColorizer(False) is plainColorizer


def testColoredOutputStillContainsTheMessage() -> None:
    output = BlockFormatter(buildColorizer(True)).format(makeRecord("Found 3 station(s)."))
    assert "Found 3 station(s)." in output


def testErrorsReportTheDomainModuleNotTheCollector(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    """The source location must point at the domain module, not at issues.py."""
    with pytest.raises(ConversionError):
        convertRows([stationRow(Latitude="")], logger)

    errorFiles = {
        record.filename for record in logCapture.records if record.levelno == logging.ERROR
    }
    assert "issues.py" not in errorFiles
    assert "stations.py" in errorFiles


def testWarningsReportTheDomainModule(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    convertRows(
        [
            stationRow(),
            elementRow(**{"ELEMENT-TYPE": "GEN", "Station 2": "", "Station 1": "Berlin_380"}),
        ],
        logger,
    )

    warningFiles = {
        record.filename for record in logCapture.records if record.levelno == logging.WARNING
    }
    assert "networkElements.py" in warningFiles
    assert "issues.py" not in warningFiles


# --------------------------------------------------------------------------- #
# --debug-file
# --------------------------------------------------------------------------- #


def testDebugFileCapturesFullDetailRegardlessOfConsoleLevel(tmp_path: Path) -> None:
    """The debug file receives DEBUG lines even when the console is at WARNING."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.WARNING)
    debugFile = tmp_path / "debug.log"

    resolved = addDebugFileHandler(logger, debugFile)
    try:
        logger.debug("only visible in the file")
        logger.warning("visible everywhere")
    finally:
        for handler in list(logger.handlers):
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)
                handler.close()

    assert resolved == debugFile.resolve()
    content = debugFile.read_text(encoding="utf-8")
    assert "only visible in the file" in content
    assert "visible everywhere" in content
    assert logger.level == logging.DEBUG, "logger must be raised so DEBUG reaches the handler"


def testDebugFileContainsNoAnsiCodes(tmp_path: Path) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    debugFile = tmp_path / "debug.log"

    addDebugFileHandler(logger, debugFile)
    try:
        logger.error("boom\nRow: 1\nField: Latitude")
    finally:
        for handler in list(logger.handlers):
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)
                handler.close()

    content = debugFile.read_text(encoding="utf-8")
    assert "\033[" not in content
    assert "Row: 1" in content


def testDebugFileCreatesParentDirectories(tmp_path: Path) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    debugFile = tmp_path / "nested" / "dir" / "debug.log"

    addDebugFileHandler(logger, debugFile)
    try:
        logger.info("hello")
    finally:
        for handler in list(logger.handlers):
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)
                handler.close()

    assert debugFile.is_file()


def testDebugFileViaCli(tmp_path: Path) -> None:
    import conftest

    from excelToCsv.cli import EXIT_SUCCESS, main

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
    inputFile = conftest.writeExcel(rows, tmp_path / "input.xlsx")
    debugFile = tmp_path / "debug.log"

    exitCode = main(
        [
            str(inputFile),
            "--output-dir",
            str(tmp_path / "out"),
            "--debug-file",
            str(debugFile),
            "--log-level",
            "WARNING",
            "--no-color",
        ]
    )

    assert exitCode == EXIT_SUCCESS
    assert debugFile.is_file()
    content = debugFile.read_text(encoding="utf-8")
    assert "DEBUG" in content
    assert "Reading input file" in content, "file has INFO detail even though console is WARNING"


# --------------------------------------------------------------------------- #
# Console default: summary instead of every single finding
# --------------------------------------------------------------------------- #


def testDetailBlocksGoToTheFindingsLogger(
    logger: logging.Logger, logCapture: RecordingHandler
) -> None:
    """Details keep a separate logger name so the console can filter them out."""
    from excelToCsv.loggingSetup import FINDINGS_LOGGER_NAME

    convertRows(
        [
            stationRow(),
            elementRow(**{"ELEMENT-TYPE": "GEN", "Station 1": "Berlin_380", "Station 2": ""}),
        ],
        logger,
    )

    detailRecords = [
        record for record in logCapture.records if record.name.startswith(FINDINGS_LOGGER_NAME)
    ]
    assert detailRecords, "the per-finding blocks still exist"
    assert any("Station reference is missing." in record.getMessage() for record in detailRecords)


def testConsoleHidesTheDetailBlocksByDefault(tmp_path: Path, capsys) -> None:
    """A default run prints the summary, not one block per finding."""
    import conftest

    from excelToCsv.cli import main

    rows = [
        stationRow(),
        *[
            elementRow(**{"ELEMENT ID": f"LINE_{index}", "Station 1": "Berlin_380",
                          "Station 2": ""})
            for index in range(4)
        ],
    ]
    inputFile = conftest.writeExcel(rows, tmp_path / "input.xlsx")

    main([str(inputFile), "-o", str(tmp_path / "out"), "--no-color"])
    quiet = capsys.readouterr().err

    assert "4x  Network element has no usable station reference." in quiet
    assert "Action: Removing the element" not in quiet, "no per-finding block"
    assert "--details" in quiet, "the summary says how to get them"

    main([str(inputFile), "-o", str(tmp_path / "out2"), "--details", "--no-color"])
    verbose = capsys.readouterr().err

    assert "Action: Removing the element" in verbose
    assert len(verbose.splitlines()) > len(quiet.splitlines())


def testSummaryGroupsByKindAndSeverity(logger: logging.Logger) -> None:
    from excelToCsv.issues import SEVERITY_ERROR, SEVERITY_WARNING, Issue, IssueCollector

    collector = IssueCollector(logger=logger)
    collector.warnings.extend([Issue(problem="w"), Issue(problem="w"), Issue(problem="other")])
    collector.errors.append(Issue(problem="boom"))

    lines = collector.summaryLines()
    assert lines[0] == f"{SEVERITY_ERROR:<7}     1x  boom", "errors first"
    assert f"{SEVERITY_WARNING:<7}     2x  w" in lines[1], "most frequent warning next"
    assert len(lines) == 3


def testCleanRunSaysSo(logger: logging.Logger, logCapture: RecordingHandler) -> None:
    convertRows([stationRow()], logger)
    assert "Validation successful - no findings." in logCapture.text(logging.INFO)


def testDebugFileKeepsTheDetailsEvenWithoutDetailsFlag(tmp_path: Path) -> None:
    """--details controls the console only; the files always get everything."""
    import conftest

    from excelToCsv.cli import main

    rows = [stationRow(), elementRow(**{"Station 1": "Berlin_380", "Station 2": ""})]
    inputFile = conftest.writeExcel(rows, tmp_path / "input.xlsx")
    debug = tmp_path / "debug.log"

    main([str(inputFile), "-o", str(tmp_path / "out"), "--debug-file", str(debug), "--no-color"])

    content = debug.read_text(encoding="utf-8")
    assert "Action: Removing the element from the output and continuing." in content
