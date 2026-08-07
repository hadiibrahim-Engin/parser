import cgmesFixtures as fx
from cgmes2excel.cgmes.identifiers import Identifier
from cgmes2excel.diagnostics import Diagnostics
from cgmes2excel.domain.network import NetworkModel
from cgmes2excel.domain.resolution import Resolution


def modelFor(tmpPath, diagnostics=None):
    diagnostics = diagnostics or Diagnostics()
    return NetworkModel(fx.sampleGraph(tmpPath, diagnostics), diagnostics)


def find(model, mrid):
    return model.graph.get(Identifier.fromRaw(mrid))


# --- resolution value object -------------------------------------------------


def testResolutionCarriesItsValueAndTrace():
    resolution = Resolution.of("Alpha", "Terminal T1", "TopologicalNode N1")
    assert resolution.found
    assert resolution.value == "Alpha"
    assert resolution.describe() == "Terminal T1 -> TopologicalNode N1"


def testEmptyResolutionExplainsWhyItIsEmpty():
    resolution = Resolution.empty("terminalWithoutNode", "Terminal T1")
    assert not resolution.found
    assert resolution.value is None
    assert resolution.reason == "terminalWithoutNode"
    assert "terminalWithoutNode" in resolution.describe()


def testResolutionCanBeExtendedWithFurtherSteps():
    resolution = Resolution.of("x", "a").then("b")
    assert resolution.trace == ("a", "b")


# --- containment -------------------------------------------------------------


def testSubstationOfEquipmentIsFoundThroughItsContainer(tmp_path):
    model = modelFor(tmp_path)
    substation = model.substationOfEquipment(find(model, "_TRA"))
    assert substation.value.name == "Umspannwerk Alpha"


def testSubstationOfEquipmentInAVoltageLevelWalksUpTheContainerChain(tmp_path):
    model = modelFor(tmp_path)
    breaker = model.graph.get(Identifier.fromRaw("_TRA"))
    breaker.contributions[0].referenceValues["Equipment.EquipmentContainer"] = [Identifier.fromRaw("#_VLA110")]
    assert model.substationOfEquipment(breaker).value.name == "Umspannwerk Alpha"


def testSubstationOfLineContainedEquipmentIsNotDerivedFromTheContainer(tmp_path):
    model = modelFor(tmp_path)
    assert not model.substationOfEquipment(find(model, "_LINE1")).found


def testVoltageLevelOfEquipmentIsResolved(tmp_path):
    model = modelFor(tmp_path)
    terminal = find(model, "_TT2")
    assert model.voltageLevelOfTerminal(terminal).value.name == "A 110kV"


def testContainmentPathListsTheFullHierarchy(tmp_path):
    model = modelFor(tmp_path)
    assert model.pathOf(find(model, "_SUBA")) == "Region Nord/Küste/Umspannwerk Alpha"


def testContainmentPathOfEquipmentIncludesItsContainers(tmp_path):
    model = modelFor(tmp_path)
    assert model.pathOf(find(model, "_TRA")) == "Region Nord/Küste/Umspannwerk Alpha/Transformator A"


def testContainmentPathOfALineUsesTheLineContainer(tmp_path):
    model = modelFor(tmp_path)
    assert model.pathOf(find(model, "_LINE1")) == "Region Nord/Küste/Stromkreis Alpha-Beta/Leitung Alpha-Beta"


# --- terminals ---------------------------------------------------------------


def testTerminalsOfEquipmentAreFoundThroughTheReverseIndex(tmp_path):
    model = modelFor(tmp_path)
    terminals = model.terminalsOf(find(model, "_LINE1"))
    assert {t.identifier.mrid for t in terminals} == {"TL1", "TL2"}


def testTerminalsAreOrderedBySequenceNumber(tmp_path):
    model = modelFor(tmp_path)
    terminals = model.terminalsOf(find(model, "_LINE1"))
    assert [t.identifier.mrid for t in terminals] == ["TL1", "TL2"]


def testSequenceNumberOrderingIgnoresDocumentOrder(tmp_path):
    body = "".join(
        [
            fx.obj("ACLineSegment", "L", fx.named("L")),
            fx.obj("Terminal", "B", fx.prop("ACDCTerminal.sequenceNumber", "2"), fx.ref("Terminal.ConductingEquipment", "L")),
            fx.obj("Terminal", "A", fx.prop("ACDCTerminal.sequenceNumber", "1"), fx.ref("Terminal.ConductingEquipment", "L")),
        ]
    )
    graph = fx.graphFrom(tmp_path, {"eq.xml": body})
    model = NetworkModel(graph, Diagnostics())
    terminals = model.terminalsOf(graph.get(Identifier.fromRaw("_L")))
    assert [t.identifier.mrid for t in terminals] == ["A", "B"]


def testTransformerTerminalsAreOrderedByWindingEndNumber(tmp_path):
    model = modelFor(tmp_path)
    terminals = model.terminalsOf(find(model, "_TRA"))
    assert [t.identifier.mrid for t in terminals] == ["TT1", "TT2"]


def testWindingEndNumberOverridesTerminalSequenceNumber(tmp_path):
    body = "".join(
        [
            fx.obj("PowerTransformer", "TR", fx.named("TR")),
            fx.obj("Terminal", "TA", fx.prop("ACDCTerminal.sequenceNumber", "1"), fx.ref("Terminal.ConductingEquipment", "TR")),
            fx.obj("Terminal", "TB", fx.prop("ACDCTerminal.sequenceNumber", "2"), fx.ref("Terminal.ConductingEquipment", "TR")),
            fx.obj("PowerTransformerEnd", "E1", fx.prop("TransformerEnd.endNumber", "2"), fx.ref("PowerTransformerEnd.PowerTransformer", "TR"), fx.ref("TransformerEnd.Terminal", "TA")),
            fx.obj("PowerTransformerEnd", "E2", fx.prop("TransformerEnd.endNumber", "1"), fx.ref("PowerTransformerEnd.PowerTransformer", "TR"), fx.ref("TransformerEnd.Terminal", "TB")),
        ]
    )
    graph = fx.graphFrom(tmp_path, {"eq.xml": body})
    model = NetworkModel(graph, Diagnostics())
    terminals = model.terminalsOf(graph.get(Identifier.fromRaw("_TR")))
    assert [t.identifier.mrid for t in terminals] == ["TB", "TA"]


def testMissingTerminalOrderingIsReportedRatherThanInvented(tmp_path):
    body = "".join(
        [
            fx.obj("ACLineSegment", "L", fx.named("L")),
            fx.obj("Terminal", "A", fx.ref("Terminal.ConductingEquipment", "L")),
            fx.obj("Terminal", "B", fx.ref("Terminal.ConductingEquipment", "L")),
        ]
    )
    diag = Diagnostics()
    graph = fx.graphFrom(tmp_path, {"eq.xml": body}, diag)
    model = NetworkModel(graph, diag)
    model.terminalsOf(graph.get(Identifier.fromRaw("_L")))
    assert "terminalOrderUndetermined" in diag.countByCode()


def testEquipmentWithoutTerminalsIsReported(tmp_path):
    body = fx.obj("ACLineSegment", "L", fx.named("L"))
    diag = Diagnostics()
    graph = fx.graphFrom(tmp_path, {"eq.xml": body}, diag)
    model = NetworkModel(graph, diag)
    assert model.terminalsOf(graph.get(Identifier.fromRaw("_L"))) == []


# --- topology traversal ------------------------------------------------------


def testTerminalResolvesToItsTopologicalNode(tmp_path):
    model = modelFor(tmp_path)
    node = model.nodeOfTerminal(find(model, "_TL1"))
    assert node.value.cimClass == "TopologicalNode"
    assert node.value.name == "Knoten A 380"


def testTerminalFallsBackToConnectivityNodeWhenTopologyIsAbsent(tmp_path):
    body = "".join(
        [
            fx.obj("ConnectivityNode", "CN", fx.named("CN 1")),
            fx.obj("Terminal", "T", fx.ref("Terminal.ConnectivityNode", "CN")),
        ]
    )
    diag = Diagnostics()
    graph = fx.graphFrom(tmp_path, {"eq.xml": body}, diag)
    model = NetworkModel(graph, diag)
    node = model.nodeOfTerminal(graph.get(Identifier.fromRaw("_T")))
    assert node.value.cimClass == "ConnectivityNode"


def testTerminalWithoutAnyNodeIsReportedAsUnresolved(tmp_path):
    body = fx.obj("Terminal", "T", fx.named("T"))
    diag = Diagnostics()
    graph = fx.graphFrom(tmp_path, {"eq.xml": body}, diag)
    model = NetworkModel(graph, diag)
    node = model.nodeOfTerminal(graph.get(Identifier.fromRaw("_T")))
    assert not node.found
    assert node.reason == "terminalWithoutNode"


def testSubstationOfATerminalIsReachedThroughTopology(tmp_path):
    model = modelFor(tmp_path)
    resolution = model.substationOfTerminal(find(model, "_TL2"))
    assert resolution.value.name == "Umspannwerk Beta"


def testSubstationOfATerminalRecordsTheTraversalItUsed(tmp_path):
    model = modelFor(tmp_path)
    trace = model.substationOfTerminal(find(model, "_TL2")).describe()
    assert "Terminal" in trace
    assert "TopologicalNode" in trace
    assert "VoltageLevel" in trace
    assert "Substation" in trace


def testSubstationOfATerminalFallsBackToConnectivityNodeContainer(tmp_path):
    body = fx.sampleEquipment()
    diag = Diagnostics()
    graph = fx.graphFrom(tmp_path, {"eq.xml": body}, diag)
    model = NetworkModel(graph, diag)
    assert model.substationOfTerminal(graph.get(Identifier.fromRaw("_TL2"))).value.name == "Umspannwerk Beta"


def testTerminalOnALineContainedNodeBorrowsTheStationOfTheOtherEquipment(tmp_path):
    body = "".join(
        [
            fx.obj("Substation", "S", fx.named("Grenzstation")),
            fx.obj("VoltageLevel", "VL", fx.named("VL"), fx.ref("VoltageLevel.Substation", "S")),
            fx.obj("Line", "LN", fx.named("Grenzleitung")),
            fx.obj("ConnectivityNode", "CN", fx.named("Grenzknoten"), fx.ref("ConnectivityNode.ConnectivityNodeContainer", "LN")),
            fx.obj("ACLineSegment", "L", fx.named("L"), fx.ref("Equipment.EquipmentContainer", "LN")),
            fx.obj("Terminal", "T1", fx.prop("ACDCTerminal.sequenceNumber", "1"), fx.ref("Terminal.ConductingEquipment", "L"), fx.ref("Terminal.ConnectivityNode", "CN")),
            fx.obj("Breaker", "B", fx.named("B"), fx.ref("Equipment.EquipmentContainer", "VL")),
            fx.obj("Terminal", "T2", fx.prop("ACDCTerminal.sequenceNumber", "1"), fx.ref("Terminal.ConductingEquipment", "B"), fx.ref("Terminal.ConnectivityNode", "CN")),
        ]
    )
    diag = Diagnostics()
    graph = fx.graphFrom(tmp_path, {"eq.xml": body}, diag)
    model = NetworkModel(graph, diag)
    assert model.substationOfTerminal(graph.get(Identifier.fromRaw("_T1"))).value.name == "Grenzstation"


# --- voltage -----------------------------------------------------------------


def testNominalVoltageOfEquipmentComesFromItsBaseVoltage(tmp_path):
    model = modelFor(tmp_path)
    assert model.nominalVoltageOf(find(model, "_LINE1")).value == 380.0


def testNominalVoltageFallsBackToTheContainerVoltageLevel(tmp_path):
    body = "".join(
        [
            fx.obj("BaseVoltage", "BV", fx.prop("BaseVoltage.nominalVoltage", "110")),
            fx.obj("Substation", "S", fx.named("S")),
            fx.obj("VoltageLevel", "VL", fx.named("VL"), fx.ref("VoltageLevel.Substation", "S"), fx.ref("VoltageLevel.BaseVoltage", "BV")),
            fx.obj("Breaker", "B", fx.named("B"), fx.ref("Equipment.EquipmentContainer", "VL")),
        ]
    )
    graph = fx.graphFrom(tmp_path, {"eq.xml": body})
    model = NetworkModel(graph, Diagnostics())
    assert model.nominalVoltageOf(graph.get(Identifier.fromRaw("_B"))).value == 110.0


def testNominalVoltageFallsBackToTheTopologicalNodeOfTheFirstTerminal(tmp_path):
    body = "".join(
        [
            fx.obj("BaseVoltage", "BV", fx.prop("BaseVoltage.nominalVoltage", "220")),
            fx.obj("TopologicalNode", "TN", fx.named("TN"), fx.ref("TopologicalNode.BaseVoltage", "BV")),
            fx.obj("ACLineSegment", "L", fx.named("L")),
            fx.obj("Terminal", "T", fx.prop("ACDCTerminal.sequenceNumber", "1"), fx.ref("Terminal.ConductingEquipment", "L"), fx.ref("Terminal.TopologicalNode", "TN")),
        ]
    )
    graph = fx.graphFrom(tmp_path, {"eq.xml": body})
    model = NetworkModel(graph, Diagnostics())
    assert model.nominalVoltageOf(graph.get(Identifier.fromRaw("_L"))).value == 220.0


def testUnavailableVoltageIsReportedRatherThanGuessed(tmp_path):
    body = fx.obj("ACLineSegment", "L", fx.named("L"))
    diag = Diagnostics()
    graph = fx.graphFrom(tmp_path, {"eq.xml": body}, diag)
    model = NetworkModel(graph, diag)
    assert not model.nominalVoltageOf(graph.get(Identifier.fromRaw("_L"))).found


def testVoltageLevelsOfASubstationAreListedHighestFirst(tmp_path):
    model = modelFor(tmp_path)
    voltages = model.nominalVoltagesOfSubstation(find(model, "_SUBA"))
    assert voltages == [380.0, 110.0]


def testSubstationWithOneVoltageLevelYieldsOneVoltage(tmp_path):
    model = modelFor(tmp_path)
    assert model.nominalVoltagesOfSubstation(find(model, "_SUBB")) == [380.0]


def testDuplicateVoltageLevelsCollapseToDistinctVoltages(tmp_path):
    body = "".join(
        [
            fx.obj("BaseVoltage", "BV", fx.prop("BaseVoltage.nominalVoltage", "110")),
            fx.obj("Substation", "S", fx.named("S")),
            fx.obj("VoltageLevel", "V1", fx.named("V1"), fx.ref("VoltageLevel.Substation", "S"), fx.ref("VoltageLevel.BaseVoltage", "BV")),
            fx.obj("VoltageLevel", "V2", fx.named("V2"), fx.ref("VoltageLevel.Substation", "S"), fx.ref("VoltageLevel.BaseVoltage", "BV")),
        ]
    )
    graph = fx.graphFrom(tmp_path, {"eq.xml": body})
    model = NetworkModel(graph, Diagnostics())
    assert model.nominalVoltagesOfSubstation(graph.get(Identifier.fromRaw("_S"))) == [110.0]


def testMultiVoltageSubstationIsAnnounced(tmp_path):
    diag = Diagnostics()
    model = modelFor(tmp_path, diag)
    model.nominalVoltagesOfSubstation(find(model, "_SUBA"))
    assert "multiVoltageSubstation" in diag.countByCode()


def testSubstationWithoutVoltageLevelsIsReported(tmp_path):
    body = fx.obj("Substation", "S", fx.named("S"))
    diag = Diagnostics()
    graph = fx.graphFrom(tmp_path, {"eq.xml": body}, diag)
    model = NetworkModel(graph, diag)
    assert model.nominalVoltagesOfSubstation(graph.get(Identifier.fromRaw("_S"))) == []
    assert "substationWithoutVoltageLevel" in diag.countByCode()


# --- regions -----------------------------------------------------------------


def testRegionOfASubstationIsTheSubGeographicalRegionName(tmp_path):
    model = modelFor(tmp_path)
    assert model.regionOf(find(model, "_SUBA")).value == "Küste"


def testMissingRegionIsEmptyRatherThanFabricated(tmp_path):
    body = fx.obj("Substation", "S", fx.named("S"))
    diag = Diagnostics()
    graph = fx.graphFrom(tmp_path, {"eq.xml": body}, diag)
    model = NetworkModel(graph, diag)
    assert not model.regionOf(graph.get(Identifier.fromRaw("_S"))).found


# --- caching -----------------------------------------------------------------


def testRepeatedTraversalsReturnTheSameResultObject(tmp_path):
    model = modelFor(tmp_path)
    terminal = find(model, "_TL1")
    assert model.substationOfTerminal(terminal) is model.substationOfTerminal(terminal)
