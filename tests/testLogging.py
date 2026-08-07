import logging
import re

from cgmes2excel.logging import (
    SUCCESS,
    ConsoleFormatter,
    PlainFormatter,
    configureLogging,
    getLogger,
)

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def makeRecord(level=logging.INFO, message="hello"):
    return logging.LogRecord("cgmes2excel.test", level, __file__, 1, message, None, None)


def testSuccessLevelSitsBetweenInfoAndWarning():
    assert logging.INFO < SUCCESS < logging.WARNING


def testSuccessLevelIsRegisteredUnderTheNameOk():
    assert logging.getLevelName(SUCCESS) == "OK"


def testLoggerExposesASuccessMethod(caplog):
    logger = getLogger("cgmes2excel.test")
    with caplog.at_level(logging.DEBUG):
        logger.success("exported %d rows", 3)
    assert "exported 3 rows" in caplog.text


def testColouredFormatterEmitsAnsiCodes():
    text = ConsoleFormatter(useColour=True).format(makeRecord(logging.WARNING))
    assert "\x1b[" in text


def testColourlessFormatterEmitsNoAnsiCodes():
    text = ConsoleFormatter(useColour=False).format(makeRecord(logging.WARNING))
    assert "\x1b[" not in text


def testEachLevelUsesADistinctColour():
    formatter = ConsoleFormatter(useColour=True)
    colours = {
        level: ANSI.findall(formatter.format(makeRecord(level)))[0]
        for level in (logging.DEBUG, logging.INFO, SUCCESS, logging.WARNING, logging.ERROR, logging.CRITICAL)
    }
    assert len(set(colours.values())) == len(colours)


def testConsoleFormatterShowsLevelAsATag():
    text = ConsoleFormatter(useColour=False).format(makeRecord(logging.WARNING, "careful"))
    assert text.startswith("[WARN]")
    assert text.endswith("careful")


def testSuccessRecordsAreTaggedOk():
    text = ConsoleFormatter(useColour=False).format(makeRecord(SUCCESS, "done"))
    assert text.startswith("[OK]")


def testPlainFormatterForFilesIsNeverColouredAndCarriesATimestamp():
    text = PlainFormatter().format(makeRecord(logging.ERROR, "boom"))
    assert "\x1b[" not in text
    assert "ERROR" in text and "boom" in text
    assert re.match(r"^\d{4}-\d{2}-\d{2}", text)


def testConfigureLoggingWritesUncolouredTextToTheLogFile(tmp_path):
    logFile = tmp_path / "run.log"
    configureLogging(verbose=False, colour=True, logFile=logFile)
    getLogger("cgmes2excel.test").warning("watch out")
    logging.shutdown()
    contents = logFile.read_text(encoding="utf-8")
    assert "watch out" in contents
    assert "\x1b[" not in contents


def testVerboseModeEnablesDebugRecords(tmp_path):
    logFile = tmp_path / "run.log"
    configureLogging(verbose=True, colour=False, logFile=logFile)
    getLogger("cgmes2excel.test").debug("fine detail")
    logging.shutdown()
    assert "fine detail" in logFile.read_text(encoding="utf-8")


def testQuietModeSuppressesDebugRecords(tmp_path):
    logFile = tmp_path / "run.log"
    configureLogging(verbose=False, colour=False, logFile=logFile)
    getLogger("cgmes2excel.test").debug("fine detail")
    logging.shutdown()
    assert "fine detail" not in logFile.read_text(encoding="utf-8")
