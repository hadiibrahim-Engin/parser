import logging

from cgmes2excel.diagnostics import Diagnostics, Issue, Severity


def testReportedIssueIsStoredWithCodeMessageAndContext():
    diag = Diagnostics()
    diag.warn("unresolvedReference", "Terminal points at unknown equipment", terminal="t1")
    (issue,) = diag.issues
    assert issue == Issue(
        code="unresolvedReference",
        severity=Severity.WARNING,
        message="Terminal points at unknown equipment",
        context={"terminal": "t1"},
    )


def testIssuesAreCountedPerCode():
    diag = Diagnostics()
    diag.warn("missingLocation", "no GL location", psr="a")
    diag.warn("missingLocation", "no GL location", psr="b")
    diag.warn("missingTerminal", "no terminal", eq="c")
    assert diag.countByCode() == {"missingLocation": 2, "missingTerminal": 1}


def testSeverityTotalsAreTracked():
    diag = Diagnostics()
    diag.warn("a", "x")
    diag.error("b", "y")
    diag.error("c", "z")
    assert diag.warningCount == 1
    assert diag.errorCount == 2


def testInfoIssuesDoNotCountAsWarningsOrErrors():
    diag = Diagnostics()
    diag.info("fallbackUsed", "used shortName instead of name")
    assert diag.warningCount == 0
    assert diag.errorCount == 0
    assert diag.countByCode() == {"fallbackUsed": 1}


def testContextIsRenderedIntoTheLoggedMessage(caplog):
    diag = Diagnostics(logger=logging.getLogger("cgmes2excel.diag"))
    with caplog.at_level(logging.DEBUG):
        diag.warn("unresolvedReference", "unknown target", terminal="t1", target="x9")
    assert "unknown target" in caplog.text
    assert "terminal=t1" in caplog.text
    assert "target=x9" in caplog.text


def testRepeatedIssuesOfOneCodeAreLoggedOnlyUpToTheCap(caplog):
    diag = Diagnostics(logger=logging.getLogger("cgmes2excel.diag"), maxLoggedPerCode=2)
    with caplog.at_level(logging.DEBUG):
        for index in range(5):
            diag.warn("missingLocation", "no GL location", psr=str(index))
    assert caplog.text.count("no GL location") == 2


def testSuppressedIssuesAreStillCollectedInFull():
    diag = Diagnostics(maxLoggedPerCode=2)
    for index in range(5):
        diag.warn("missingLocation", "no GL location", psr=str(index))
    assert diag.countByCode() == {"missingLocation": 5}


def testSuppressionIsReportedOnceTheRunIsSummarised(caplog):
    diag = Diagnostics(logger=logging.getLogger("cgmes2excel.diag"), maxLoggedPerCode=2)
    for index in range(5):
        diag.warn("missingLocation", "no GL location", psr=str(index))
    with caplog.at_level(logging.DEBUG):
        diag.logSuppressionSummary()
    assert "missingLocation" in caplog.text
    assert "3" in caplog.text


def testEmptyFieldReasonsAreTrackedSeparatelyFromIssues():
    diag = Diagnostics()
    diag.noteEmptyField("Stationen", "MJAP-ID", "notPresentInCgmes")
    diag.noteEmptyField("Stationen", "MJAP-ID", "notPresentInCgmes")
    diag.noteEmptyField("NETZELEMENTE", "IBN", "notPresentInCgmes")
    assert diag.emptyFieldCount == 3
    assert diag.emptyFieldsBySheet()["Stationen"]["MJAP-ID"] == 2
    assert diag.issues == []


def testDiagnosticsStartOutEmpty():
    diag = Diagnostics()
    assert diag.issues == []
    assert diag.countByCode() == {}
    assert diag.emptyFieldCount == 0
