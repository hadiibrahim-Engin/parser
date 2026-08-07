import cgmesFixtures as fx
from cgmes2excel.cgmes.identifiers import Identifier
from cgmes2excel.diagnostics import Diagnostics
from cgmes2excel.domain.classification import EquipmentRegistry
from cgmes2excel.domain.geography import GeographyResolver
from cgmes2excel.domain.network import NetworkModel
from cgmes2excel.mapping.elements import NETZELEMENTE_RULES, buildElementRows
from cgmes2excel.mapping.rows import RowBuilder
from cgmes2excel.mapping.schema import NETZELEMENTE, STATIONEN
from cgmes2excel.mapping.stations import STATIONEN_RULES, buildStationRows


class Context:
    def __init__(self, tmpPath, documents=None, diagnostics=None, registry=None):
        self.diagnostics = diagnostics or Diagnostics()
        documents = documents if documents is not None else {
            "eq.xml": fx.sampleEquipment(),
            "tp.xml": fx.sampleTopology(),
            "gl.xml": fx.sampleGeography(),
        }
        self.graph = fx.graphFrom(tmpPath, documents, self.diagnostics)
        self.model = NetworkModel(self.graph, self.diagnostics)
        self.geography = GeographyResolver(self.graph, self.diagnostics)
        self.registry = registry or EquipmentRegistry.withDefaults()

    def stations(self):
        return buildStationRows(self.model, self.geography, self.diagnostics)

    def elements(self):
        return buildElementRows(self.model, self.geography, self.registry, self.diagnostics)

    def find(self, mrid):
        return self.graph.get(Identifier.fromRaw(mrid))


def cell(row, column):
    return row.value(column)


def stationNamed(rows, name):
    return next(row for row in rows if row.value("Stationname") == name)


def elementNamed(rows, title):
    return next(row for row in rows if row.value("Title") == title)


# --- rule completeness -------------------------------------------------------


def testEveryStationenColumnHasExactlyOneRule():
    assert [rule.column for rule in STATIONEN_RULES] == list(STATIONEN.columns)


def testEveryNetzelementeColumnHasExactlyOneRule():
    assert [rule.column for rule in NETZELEMENTE_RULES] == list(NETZELEMENTE.columns)


def testEveryRuleDocumentsItsSource():
    for rule in (*STATIONEN_RULES, *NETZELEMENTE_RULES):
        assert rule.description


def testRowBuilderRejectsRulesThatDoNotCoverTheSchema():
    import pytest

    from cgmes2excel.mapping.schema import SchemaViolation

    with pytest.raises(SchemaViolation):
        RowBuilder(STATIONEN, STATIONEN_RULES[:-1])


# --- Stationen ---------------------------------------------------------------


def testOneRowPerSubstation(tmp_path):
    rows = Context(tmp_path).stations()
    assert len(rows) == 2


def testMultiVoltageSubstationStillProducesASingleRow(tmp_path):
    rows = Context(tmp_path).stations()
    assert [row.value("Stationname") for row in rows].count("Umspannwerk Alpha") == 1


def testStationRowsHaveTheContractedWidth(tmp_path):
    for row in Context(tmp_path).stations():
        assert len(row.values) == 22


def testStationNameComesFromTheIdentifiedObjectName(tmp_path):
    rows = Context(tmp_path).stations()
    assert stationNamed(rows, "Umspannwerk Alpha")


def testStationShortNameIsExported(tmp_path):
    row = stationNamed(Context(tmp_path).stations(), "Umspannwerk Alpha")
    assert cell(row, "Stationsname - Kurzname") == "UWA"


def testStationVoltageCombinesEveryVoltageLevelHighestFirst(tmp_path):
    row = stationNamed(Context(tmp_path).stations(), "Umspannwerk Alpha")
    assert cell(row, "Spannung") == "380/110"


def testSingleVoltageStationShowsOneVoltage(tmp_path):
    row = stationNamed(Context(tmp_path).stations(), "Umspannwerk Beta")
    assert cell(row, "Spannung") == "380"


def testStationCoordinatesComeFromTheGlProfile(tmp_path):
    row = stationNamed(Context(tmp_path).stations(), "Umspannwerk Alpha")
    assert cell(row, "lat") == 53.551086
    assert cell(row, "long") == 9.993682


def testStationCoordinatesAreEmptyWithoutAGlProfile(tmp_path):
    context = Context(tmp_path, documents={"eq.xml": fx.sampleEquipment()})
    row = stationNamed(context.stations(), "Umspannwerk Alpha")
    assert cell(row, "lat") is None
    assert cell(row, "long") is None


def testStationGuidIsTheCgmesMrid(tmp_path):
    row = stationNamed(Context(tmp_path).stations(), "Umspannwerk Alpha")
    assert cell(row, "ID-GUID intern-1") == "SUBA"


def testStationElementTypeIsItsCimClass(tmp_path):
    row = stationNamed(Context(tmp_path).stations(), "Umspannwerk Alpha")
    assert cell(row, "Elementtyp") == "Substation"


def testStationPathFollowsTheGeographicalHierarchy(tmp_path):
    row = stationNamed(Context(tmp_path).stations(), "Umspannwerk Alpha")
    assert cell(row, "Pfad") == "Region Nord/Küste/Umspannwerk Alpha"


def testOrganisationSpecificStationColumnsStayEmpty(tmp_path):
    row = stationNamed(Context(tmp_path).stations(), "Umspannwerk Alpha")
    for column in ("Eigentümer", "MJAP-ID", "IBN", "ABN", "reales UW", "ID-OPC", "ID-UCTE", "relevant für", "Geändert", "Geändert von"):
        assert cell(row, column) is None


def testEmptyColumnsAreRecordedWithAReason(tmp_path):
    context = Context(tmp_path)
    context.stations()
    assert context.diagnostics.emptyFieldsBySheet()["Stationen"]["MJAP-ID"] == 2
    assert context.diagnostics.emptyFieldReason("Stationen", "MJAP-ID")


def testStationsAreExportedInAStableOrder(tmp_path):
    first = [row.value("ID-GUID intern-1") for row in Context(tmp_path).stations()]
    second = [row.value("ID-GUID intern-1") for row in Context(tmp_path).stations()]
    assert first == second


# --- NETZELEMENTE ------------------------------------------------------------


def testOnlyIncludedEquipmentClassesBecomeRows(tmp_path):
    rows = Context(tmp_path).elements()
    assert {row.value("Element Typ") for row in rows} == {"ACLineSegment", "PowerTransformer"}


def testSwitchgearIsExcludedByDefaultButCanBeSwitchedOn(tmp_path):
    body = fx.sampleEquipment() + fx.obj("Breaker", "BR", fx.named("Leistungsschalter"), fx.ref("Equipment.EquipmentContainer", "VLA380"))
    withoutSwitches = Context(tmp_path, documents={"eq.xml": body})
    assert not any(row.value("Element Typ") == "Breaker" for row in withoutSwitches.elements())

    withSwitches = Context(
        tmp_path,
        documents={"eq.xml": body},
        registry=EquipmentRegistry.withDefaults().including("Breaker"),
    )
    assert any(row.value("Element Typ") == "Breaker" for row in withSwitches.elements())


def testElementRowsHaveTheContractedWidth(tmp_path):
    for row in Context(tmp_path).elements():
        assert len(row.values) == 27


def testLineTitleIsTheEquipmentName(tmp_path):
    rows = Context(tmp_path).elements()
    assert elementNamed(rows, "Leitung Alpha-Beta")


def testCircuitShortNameComesFromTheContainingLine(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    assert cell(row, "Stromkreisname - Kurzname") == "SK-AB"


def testLineVoltageIsNumeric(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    assert cell(row, "Spannung") == 380.0


def testLineStartStationIsDerivedFromItsFirstTerminal(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    assert cell(row, "Station Anfang") == "Umspannwerk Alpha"


def testLineEndStationIsDerivedFromItsSecondTerminal(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    assert cell(row, "Station Ende") == "Umspannwerk Beta"


def testLineNodesAreTheTopologicalNodeNames(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    assert cell(row, "Y-Knoten-1") == "Knoten A 380"
    assert cell(row, "Y-Knoten-2") == "Knoten B 380"


def testLineNodesFallBackToConnectivityNodesWithoutTopology(tmp_path):
    context = Context(tmp_path, documents={"eq.xml": fx.sampleEquipment()})
    row = elementNamed(context.elements(), "Leitung Alpha-Beta")
    assert cell(row, "Y-Knoten-1") == "CN A 380"


def testLineLeavesTheTransformerStationColumnsEmpty(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    assert cell(row, "Station T-1") is None
    assert cell(row, "Station T-2") is None


def testTransformerUsesTheTransformerStationColumns(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Transformator A")
    assert cell(row, "Station T-1") == "Umspannwerk Alpha"
    assert cell(row, "Station T-2") == "Umspannwerk Alpha"


def testTransformerReportsItsOwnStationAsTheStartStation(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Transformator A")
    assert cell(row, "Station Anfang") == "Umspannwerk Alpha"
    assert cell(row, "Station Ende") is None


def testTransformerNodesSpanBothVoltageLevels(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Transformator A")
    assert cell(row, "Y-Knoten-1") == "Knoten A 380"
    assert cell(row, "Y-Knoten-2") == "Knoten A 110"


def testSingleTerminalEquipmentReportsOnlyAStartStation(tmp_path):
    body = fx.sampleEquipment() + "".join(
        [
            fx.obj("EnergyConsumer", "EC", fx.named("Last Alpha"), fx.ref("Equipment.EquipmentContainer", "VLA110")),
            fx.obj("Terminal", "TEC", fx.prop("ACDCTerminal.sequenceNumber", "1"), fx.ref("Terminal.ConductingEquipment", "EC"), fx.ref("Terminal.ConnectivityNode", "CNA110")),
        ]
    )
    context = Context(
        tmp_path,
        documents={"eq.xml": body},
        registry=EquipmentRegistry.withDefaults().including("EnergyConsumer"),
    )
    row = elementNamed(context.elements(), "Last Alpha")
    assert cell(row, "Station Anfang") == "Umspannwerk Alpha"
    assert cell(row, "Station Ende") is None
    assert cell(row, "Y-Knoten-2") is None


def testElementRegionIsTheSubGeographicalRegion(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    assert cell(row, "Region") == "Küste"


def testElementRegionFallsBackToTheRegionOfItsStartStation(tmp_path):
    body = "".join(
        [
            fx.obj("GeographicalRegion", "GR", fx.named("Nord")),
            fx.obj("SubGeographicalRegion", "SGR", fx.named("Küste"), fx.ref("SubGeographicalRegion.Region", "GR")),
            fx.obj("Substation", "S", fx.named("Alpha"), fx.ref("Substation.Region", "SGR")),
            fx.obj("VoltageLevel", "VL", fx.named("VL"), fx.ref("VoltageLevel.Substation", "S")),
            fx.obj("ConnectivityNode", "CN", fx.named("CN"), fx.ref("ConnectivityNode.ConnectivityNodeContainer", "VL")),
            fx.obj("Line", "LN", fx.named("Leitungszug ohne Region")),
            fx.obj("ACLineSegment", "L", fx.named("Leitung"), fx.ref("Equipment.EquipmentContainer", "LN")),
            fx.obj("Terminal", "T1", fx.prop("ACDCTerminal.sequenceNumber", "1"), fx.ref("Terminal.ConductingEquipment", "L"), fx.ref("Terminal.ConnectivityNode", "CN")),
            fx.obj("Terminal", "T2", fx.prop("ACDCTerminal.sequenceNumber", "2"), fx.ref("Terminal.ConductingEquipment", "L")),
        ]
    )
    context = Context(tmp_path, documents={"eq.xml": body})
    row = elementNamed(context.elements(), "Leitung")
    assert cell(row, "Region") == "Küste"


def testElementPathFollowsItsContainer(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    assert cell(row, "Pfad") == "Region Nord/Küste/Stromkreis Alpha-Beta/Leitung Alpha-Beta"


def testElementGuidIsTheCgmesMrid(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    assert cell(row, "ID-GUID intern-1") == "LINE1"


def testOrganisationSpecificElementColumnsStayEmpty(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    for column in ("Eigentümer", "MJAP-ID", "IBN", "ABN", "relevant für", "ID-OPC", "ID-UCTE", "ID", "Geändert", "Geändert von"):
        assert cell(row, column) is None


def testThreeWindingTransformerReportsTheWindingTheSheetCannotHold(tmp_path):
    body = fx.sampleEquipment() + "".join(
        [
            fx.obj("Terminal", "TT3", fx.prop("ACDCTerminal.sequenceNumber", "3"), fx.ref("Terminal.ConductingEquipment", "TRA"), fx.ref("Terminal.ConnectivityNode", "CNB380")),
            fx.obj("PowerTransformerEnd", "TE3", fx.prop("TransformerEnd.endNumber", "3"), fx.ref("PowerTransformerEnd.PowerTransformer", "TRA"), fx.ref("TransformerEnd.Terminal", "TT3")),
        ]
    )
    context = Context(tmp_path, documents={"eq.xml": body})
    context.elements()
    assert "terminalsBeyondTargetFormat" in context.diagnostics.countByCode()


def testTwoTerminalEquipmentDoesNotTriggerTheTruncationWarning(tmp_path):
    context = Context(tmp_path)
    context.elements()
    assert "terminalsBeyondTargetFormat" not in context.diagnostics.countByCode()


def testEquipmentWithUnexpectedTerminalCountIsReported(tmp_path):
    body = fx.sampleEquipment() + "".join(
        [
            fx.obj("ACLineSegment", "L3", fx.named("Stichleitung"), fx.ref("Equipment.EquipmentContainer", "LINEC")),
            fx.obj("Terminal", "T3", fx.prop("ACDCTerminal.sequenceNumber", "1"), fx.ref("Terminal.ConductingEquipment", "L3"), fx.ref("Terminal.ConnectivityNode", "CNA380")),
        ]
    )
    context = Context(tmp_path, documents={"eq.xml": body})
    context.elements()
    assert "unexpectedTerminalCount" in context.diagnostics.countByCode()


# --- traceability ------------------------------------------------------------


def testRowRecordsHowEachValueWasDerived(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    trace = row.traceOf("Station Anfang")
    assert "Terminal" in trace
    assert "TopologicalNode" in trace
    assert "VoltageLevel" in trace
    assert "Umspannwerk Alpha" in trace


def testEmptyCellTraceExplainsWhyItIsEmpty(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    assert "unavailable" in row.traceOf("MJAP-ID")


def testRowKnowsWhichCimObjectItCameFrom(tmp_path):
    row = elementNamed(Context(tmp_path).elements(), "Leitung Alpha-Beta")
    assert row.sourceMrid == "LINE1"
