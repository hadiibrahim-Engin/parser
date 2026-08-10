"""Filesystem validation rules. No Qt is imported here."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from cgmesparser.gui.core.request import ConversionRequest
from cgmesparser.gui.core.states import CheckStatus, InputRole
from cgmesparser.gui.core.validation import InputCheck, ValidationReport, validateRequest


def statusFor(request: ConversionRequest, role: InputRole) -> CheckStatus:
    check = validateRequest(request).checkFor(role)
    assert check is not None
    return check.status


def messageFor(request: ConversionRequest, role: InputRole) -> str:
    check = validateRequest(request).checkFor(role)
    assert check is not None
    return check.message


class TestEmptyRequest:
    def testEveryRoleIsReportedAsNotSelected(self) -> None:
        report = validateRequest(ConversionRequest())
        assert len(report.checks) == len(InputRole)
        assert all(check.status is CheckStatus.ERROR for check in report.checks)
        assert all(check.message == "Not selected" for check in report.checks)

    def testEmptyRequestIsNotValid(self) -> None:
        assert validateRequest(ConversionRequest()).isValid is False

    def testSummaryCountsErrors(self) -> None:
        assert validateRequest(ConversionRequest()).summary == "4 problems found"


class TestProfileZip:
    def testAcceptsAReadableNonEmptyZip(self, validRequest: ConversionRequest) -> None:
        assert statusFor(validRequest, InputRole.PROFILE_ZIP) is CheckStatus.OK

    def testRejectsAMissingFile(self, validRequest: ConversionRequest, tmp_path: Path) -> None:
        request = validRequest.withPath(InputRole.PROFILE_ZIP, tmp_path / "absent.zip")
        assert messageFor(request, InputRole.PROFILE_ZIP) == "File does not exist"

    def testRejectsADirectory(self, validRequest: ConversionRequest, tmp_path: Path) -> None:
        request = validRequest.withPath(InputRole.PROFILE_ZIP, tmp_path / "snapshot")
        assert messageFor(request, InputRole.PROFILE_ZIP) == "Not a file"

    def testRejectsANonZipSuffix(self, validRequest: ConversionRequest, tmp_path: Path) -> None:
        other = tmp_path / "profile.rar"
        other.write_bytes(b"x")
        request = validRequest.withPath(InputRole.PROFILE_ZIP, other)
        assert messageFor(request, InputRole.PROFILE_ZIP) == "Not a .zip archive"

    def testRejectsAnEmptyFile(self, validRequest: ConversionRequest, tmp_path: Path) -> None:
        empty = tmp_path / "empty.zip"
        empty.write_bytes(b"")
        request = validRequest.withPath(InputRole.PROFILE_ZIP, empty)
        assert messageFor(request, InputRole.PROFILE_ZIP) == "File is empty"

    def testSuffixCheckIsCaseInsensitive(self, validRequest: ConversionRequest, tmp_path: Path) -> None:
        upper = tmp_path / "profile.ZIP"
        upper.write_bytes(b"PK\x05\x06")
        request = validRequest.withPath(InputRole.PROFILE_ZIP, upper)
        assert statusFor(request, InputRole.PROFILE_ZIP) is CheckStatus.OK


@pytest.mark.parametrize("role", [InputRole.SNAPSHOT_DATASET, InputRole.CIM_CACHE_DATASET])
class TestDatasets:
    def testAcceptsAPopulatedDirectory(self, validRequest: ConversionRequest, role: InputRole) -> None:
        assert statusFor(validRequest, role) is CheckStatus.OK

    def testAcceptsASingleFile(
        self, validRequest: ConversionRequest, role: InputRole, tmp_path: Path
    ) -> None:
        document = tmp_path / "single.xml"
        document.write_text("<rdf/>", encoding="utf-8")
        assert statusFor(validRequest.withPath(role, document), role) is CheckStatus.OK

    def testWarnsOnAnEmptyDirectory(
        self, validRequest: ConversionRequest, role: InputRole, tmp_path: Path
    ) -> None:
        empty = tmp_path / f"empty-{role.name}"
        empty.mkdir()
        request = validRequest.withPath(role, empty)
        assert statusFor(request, role) is CheckStatus.WARNING
        assert messageFor(request, role) == "Directory is empty"

    def testAnEmptyDirectoryStillAllowsConversion(
        self, validRequest: ConversionRequest, role: InputRole, tmp_path: Path
    ) -> None:
        empty = tmp_path / f"empty2-{role.name}"
        empty.mkdir()
        assert validateRequest(validRequest.withPath(role, empty)).isValid is True

    def testRejectsAMissingPath(
        self, validRequest: ConversionRequest, role: InputRole, tmp_path: Path
    ) -> None:
        request = validRequest.withPath(role, tmp_path / "gone")
        assert messageFor(request, role) == "Path does not exist"


class TestOutputDirectory:
    def testAnExistingDirectoryIsAWarningNotAnError(self, validRequest: ConversionRequest) -> None:
        # It is usable, but earlier output in it may be overwritten. The mock-up
        # shows this as amber, and warnings must not block a run.
        assert statusFor(validRequest, InputRole.OUTPUT_DIRECTORY) is CheckStatus.WARNING
        assert messageFor(validRequest, InputRole.OUTPUT_DIRECTORY) == "Directory exists"
        assert validateRequest(validRequest).isValid is True

    def testAMissingDirectoryWithAWritableParentWillBeCreated(
        self, validRequest: ConversionRequest, tmp_path: Path
    ) -> None:
        request = validRequest.withPath(InputRole.OUTPUT_DIRECTORY, tmp_path / "new")
        assert messageFor(request, InputRole.OUTPUT_DIRECTORY) == "Will be created"
        assert validateRequest(request).isValid is True

    def testRejectsAMissingParent(self, validRequest: ConversionRequest, tmp_path: Path) -> None:
        request = validRequest.withPath(InputRole.OUTPUT_DIRECTORY, tmp_path / "absent" / "deep")
        assert messageFor(request, InputRole.OUTPUT_DIRECTORY) == "Parent directory does not exist"

    def testRejectsAFileWhereADirectoryIsExpected(
        self, validRequest: ConversionRequest, tmp_path: Path
    ) -> None:
        document = tmp_path / "notADirectory.txt"
        document.write_text("x", encoding="utf-8")
        request = validRequest.withPath(InputRole.OUTPUT_DIRECTORY, document)
        assert messageFor(request, InputRole.OUTPUT_DIRECTORY) == "Not a directory"

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits do not apply on Windows")
    def testRejectsAnUnwritableDirectory(
        self, validRequest: ConversionRequest, tmp_path: Path
    ) -> None:
        locked = tmp_path / "locked"
        locked.mkdir(mode=0o500)
        try:
            request = validRequest.withPath(InputRole.OUTPUT_DIRECTORY, locked)
            assert messageFor(request, InputRole.OUTPUT_DIRECTORY) == "Directory is not writable"
        finally:
            locked.chmod(0o700)


class TestReport:
    def testWarningsDoNotBlockButErrorsDo(self) -> None:
        warning = InputCheck(InputRole.OUTPUT_DIRECTORY, CheckStatus.WARNING, "Directory exists")
        error = InputCheck(InputRole.PROFILE_ZIP, CheckStatus.ERROR, "Not selected")
        assert ValidationReport((warning,)).isValid is True
        assert ValidationReport((warning, error)).isValid is False

    def testSummaryIsSingularForOneProblem(self) -> None:
        error = InputCheck(InputRole.PROFILE_ZIP, CheckStatus.ERROR, "Not selected")
        assert ValidationReport((error,)).summary == "1 problem found"

    def testSummaryReadsAsValidatedWhenOnlyWarningsArePresent(
        self, validRequest: ConversionRequest
    ) -> None:
        assert validateRequest(validRequest).summary == "Inputs validated"

    def testCountsAreReported(self, validRequest: ConversionRequest) -> None:
        report = validateRequest(validRequest)
        assert report.errorCount == 0
        assert report.warningCount == 1


class TestExtraCheckers:
    def testDomainChecksCanBeAppendedWithoutTouchingTheInterface(
        self, validRequest: ConversionRequest
    ) -> None:
        def refuseEverything(request: ConversionRequest):
            yield InputCheck(InputRole.SNAPSHOT_DATASET, CheckStatus.ERROR, "No SSH profile present")

        report = validateRequest(validRequest, (refuseEverything,))
        assert report.isValid is False
        assert report.checks[-1].message == "No SSH profile present"
