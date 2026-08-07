"""Orchestration of one conversion run.

Discovery -> parsing -> indexing -> profile detection -> semantic derivation ->
mapping -> export -> validation -> summary. Each stage is independently
testable; this module only sequences them and reports what happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from cgmes2excel.cgmes.graph import CimGraph
from cgmes2excel.cgmes.profiles import DocumentProfile, Profile, ProfileEvidence, detectProfile
from cgmes2excel.cgmes.reader import MalformedDocumentError
from cgmes2excel.diagnostics import Diagnostics
from cgmes2excel.domain.classification import EquipmentRegistry
from cgmes2excel.domain.geography import GeographyResolver
from cgmes2excel.domain.network import NetworkModel
from cgmes2excel.export.excel import writeWorkbook
from cgmes2excel.export.validation import ValidationResult, validateWorkbook
from cgmes2excel.inputs import DocumentSource, discoverDocuments, readDocument
from cgmes2excel.logging import getLogger
from cgmes2excel.mapping.elements import buildElementRows
from cgmes2excel.mapping.rows import Row
from cgmes2excel.mapping.stations import buildStationRows

logger = getLogger("cgmes2excel.pipeline")

_EXPECTED_PROFILES = (Profile.EQ, Profile.SSH, Profile.TP, Profile.SV, Profile.GL)

_INTERESTING_CLASSES = (
    "Substation",
    "VoltageLevel",
    "BaseVoltage",
    "Bay",
    "ACLineSegment",
    "PowerTransformer",
    "PowerTransformerEnd",
    "Terminal",
    "ConnectivityNode",
    "TopologicalNode",
    "Breaker",
    "Disconnector",
    "BusbarSection",
    "SynchronousMachine",
    "EnergyConsumer",
    "Location",
    "PositionPoint",
)


class NoDocumentsError(Exception):
    """Raised when the inputs contain no CGMES document at all."""


@dataclass(slots=True)
class ConversionOptions:
    """Everything that steers one run."""

    inputs: list[Path]
    output: Path
    includeClasses: list[str] = field(default_factory=list)
    onlyClasses: list[str] = field(default_factory=list)
    traceFile: Path | None = None

    def registry(self) -> EquipmentRegistry:
        registry = EquipmentRegistry.withDefaults()
        if self.onlyClasses:
            return registry.onlyIncluding(*self.onlyClasses)
        if self.includeClasses:
            return registry.including(*self.includeClasses)
        return registry


@dataclass(slots=True)
class Summary:
    """The numbers reported at the end of a run."""

    documents: int = 0
    detectedProfiles: list[str] = field(default_factory=list)
    missingProfiles: list[str] = field(default_factory=list)
    totalObjects: int = 0
    classCounts: dict[str, int] = field(default_factory=dict)
    stationRows: int = 0
    elementRows: int = 0
    warnings: int = 0
    errors: int = 0
    unresolvedReferences: int = 0
    unsupportedObjects: int = 0
    emptyFields: int = 0
    cimVersions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConversionResult:
    """Everything a caller may want to inspect after a run."""

    output: Path
    documents: list[DocumentProfile]
    graph: CimGraph
    stationRows: list[Row]
    elementRows: list[Row]
    validation: ValidationResult
    diagnostics: Diagnostics
    summary: Summary


def convert(options: ConversionOptions) -> ConversionResult:
    """Convert a CGMES export into the contracted workbook."""
    diagnostics = Diagnostics(logger=getLogger("cgmes2excel.diagnostics"))

    logger.info("Loading CGMES input files...")
    sources = discoverDocuments(options.inputs)
    if not sources:
        raise NoDocumentsError(f"No CGMES documents found in: {', '.join(str(p) for p in options.inputs)}")
    logger.success("Found %d CGMES document(s)", len(sources))

    graph = CimGraph(diagnostics=diagnostics)
    documents = _parseDocuments(sources, graph, diagnostics)
    logger.success("Parsed %s CIM objects from %d document(s)", f"{len(graph):,}", len(documents))
    _logClassCounts(graph)

    logger.info("Resolving cross-profile references...")
    dangling = graph.verifyReferences()
    if dangling:
        logger.warning("%d reference(s) point at objects that are not in the export", dangling)
    else:
        logger.success("All references resolved")

    logger.info("Deriving the network model...")
    model = NetworkModel(graph, diagnostics)
    geography = GeographyResolver(graph, diagnostics)
    registry = options.registry()

    stationRows = buildStationRows(model, geography, diagnostics)
    logger.success("Derived %d station(s)", len(stationRows))

    elementRows = buildElementRows(model, geography, registry, diagnostics)
    logger.success(
        "Derived %d network element(s) from %s",
        len(elementRows),
        ", ".join(registry.includedClasses()),
    )

    unsupported = _reportUnsupportedClasses(graph, registry, diagnostics)

    logger.info("Writing workbook to %s", options.output)
    writeWorkbook(options.output, {"Stationen": stationRows, "NETZELEMENTE": elementRows}, diagnostics)

    validation = validateWorkbook(options.output)
    for violation in validation.violations:
        diagnostics.error("schemaViolation", violation)

    if options.traceFile is not None:
        _writeTraceReport(options.traceFile, stationRows, elementRows)
        logger.info("Wrote derivation trace to %s", options.traceFile)

    diagnostics.logSuppressionSummary()

    summary = _buildSummary(documents, graph, stationRows, elementRows, diagnostics, unsupported)
    result = ConversionResult(
        output=options.output,
        documents=documents,
        graph=graph,
        stationRows=stationRows,
        elementRows=elementRows,
        validation=validation,
        diagnostics=diagnostics,
        summary=summary,
    )
    logSummary(result)
    return result


def _parseDocuments(
    sources: list[DocumentSource],
    graph: CimGraph,
    diagnostics: Diagnostics,
) -> list[DocumentProfile]:
    documents: list[DocumentProfile] = []
    for source in sources:
        evidence = ProfileEvidence()
        try:
            for raw in readDocument(source):
                evidence.note(raw)
                graph.add(raw)
        except MalformedDocumentError as exc:
            diagnostics.error(
                "malformedDocument",
                "Document is not well-formed XML and was skipped",
                document=source.name,
                reason=exc.reason,
            )
            continue
        document = detectProfile(source.displayPath, evidence, diagnostics)
        documents.append(document)
        logger.info(
            "Detected profile %s: %s (%s object(s), by %s)",
            document.profile.value,
            source.name,
            f"{document.objectCount:,}",
            document.detectedBy.value,
        )
    return documents


def _logClassCounts(graph: CimGraph) -> None:
    counts = graph.classCounts()
    for cimClass in _INTERESTING_CLASSES:
        if cimClass in counts:
            logger.debug("  %-22s %s", cimClass, f"{counts[cimClass]:,}")


def _reportUnsupportedClasses(
    graph: CimGraph,
    registry: EquipmentRegistry,
    diagnostics: Diagnostics,
) -> int:
    """Count known equipment classes present in the model but not exported."""
    total = 0
    for cimClass, count in sorted(graph.classCounts().items()):
        if registry.isKnown(cimClass) and not registry.isIncluded(cimClass):
            total += count
            diagnostics.info(
                "equipmentClassNotExported",
                "Equipment class is present but not part of the exported set",
                cimClass=cimClass,
                objects=count,
            )
    return total


def _writeTraceReport(path: Path, stationRows: list[Row], elementRows: list[Row]) -> None:
    lines: list[str] = []
    for sheet, rows in (("Stationen", stationRows), ("NETZELEMENTE", elementRows)):
        for number, row in enumerate(rows, start=1):
            lines.append(f"{sheet} row {number} (source mRID {row.sourceMrid})")
            for column in row.columns:
                lines.append(f"    {column}: {row.traceOf(column)}")
            lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _buildSummary(
    documents: list[DocumentProfile],
    graph: CimGraph,
    stationRows: list[Row],
    elementRows: list[Row],
    diagnostics: Diagnostics,
    unsupported: int,
) -> Summary:
    detected = {document.profile for document in documents}
    versions = sorted({document.cimNamespace for document in documents if document.cimNamespace})
    return Summary(
        documents=len(documents),
        detectedProfiles=[profile.value for profile in _EXPECTED_PROFILES if profile in detected],
        missingProfiles=[profile.value for profile in _EXPECTED_PROFILES if profile not in detected],
        totalObjects=len(graph),
        classCounts=graph.classCounts(),
        stationRows=len(stationRows),
        elementRows=len(elementRows),
        warnings=diagnostics.warningCount,
        errors=diagnostics.errorCount,
        unresolvedReferences=diagnostics.unresolvedReferenceCount,
        unsupportedObjects=unsupported,
        emptyFields=diagnostics.emptyFieldCount,
        cimVersions=versions,
    )


def logSummary(result: ConversionResult) -> None:
    """Print the end-of-run report."""
    summary = result.summary
    logger.success("Conversion completed")

    logger.info("Input: %d CGMES document(s)", summary.documents)
    for profile in summary.detectedProfiles:
        logger.info("  %s detected", profile)
    for profile in summary.missingProfiles:
        logger.warning("  %s not present in the export", profile)

    logger.info("Parsed: %s total CIM objects", f"{summary.totalObjects:,}")
    for cimClass in _INTERESTING_CLASSES:
        count = summary.classCounts.get(cimClass)
        if count:
            logger.info("  %-22s %s", cimClass, f"{count:,}")

    logger.info("Output: %d Stationen row(s), %d NETZELEMENTE row(s)", summary.stationRows, summary.elementRows)

    logger.info("Data quality:")
    _logCount(summary.warnings, "  %d warning(s)")
    _logCount(summary.errors, "  %d error(s)", isError=True)
    _logCount(summary.unresolvedReferences, "  %d unresolved reference(s)")
    _logCount(summary.unsupportedObjects, "  %d object(s) of classes that are not exported")
    logger.info("  %s empty target field(s) with no source information", f"{summary.emptyFields:,}")

    for sheet, passed in result.validation.sheetResults.items():
        if passed:
            logger.success("Excel schema %s: PASS", sheet)
        else:
            logger.error("Excel schema %s: FAIL", sheet)

    logger.success("Output: %s", result.output)


def _logCount(count: int, template: str, isError: bool = False) -> None:
    if count == 0:
        logger.info(template, count)
    elif isError:
        logger.error(template, count)
    else:
        logger.warning(template, count)
