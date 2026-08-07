from pathlib import Path

from cgmes2excel.cgmes.graph import CimGraph
from cgmes2excel.cgmes.identifiers import Identifier
from cgmes2excel.cgmes.reader import RawObject
from cgmes2excel.diagnostics import Diagnostics

CIM16 = "http://iec.ch/TC57/2013/CIM-schema-cim16#"


def rawObject(rdfId, cimClass, source="eq.xml", order=0, isAbout=False, literals=None, refs=None):
    obj = RawObject(
        identifier=Identifier.fromRaw(rdfId),
        cimClass=cimClass,
        classNamespace=CIM16,
        source=Path(source),
        documentOrder=order,
        isAbout=isAbout,
    )
    for name, value in (literals or {}).items():
        obj.addLiteral(name, value)
    for name, value in (refs or {}).items():
        obj.addReference(name, Identifier.fromRaw(value))
    return obj


def testObjectCanBeLookedUpByItsIdentifier():
    graph = CimGraph()
    graph.add(rawObject("_sub1", "Substation"))
    found = graph.get(Identifier.fromRaw("#_sub1"))
    assert found is not None
    assert found.cimClass == "Substation"


def testLookupAcceptsAnyReferenceSpelling():
    graph = CimGraph()
    graph.add(rawObject("_sub1", "Substation"))
    assert graph.get(Identifier.fromRaw("urn:uuid:SUB1")) is not None


def testUnknownIdentifierResolvesToNone():
    graph = CimGraph()
    assert graph.get(Identifier.fromRaw("_nope")) is None


def testForwardReferenceResolvesEvenWhenTargetIsAddedLater():
    graph = CimGraph()
    graph.add(rawObject("_vl", "VoltageLevel", refs={"VoltageLevel.Substation": "#_sub1"}))
    graph.add(rawObject("_sub1", "Substation", order=1))
    voltageLevel = graph.get(Identifier.fromRaw("_vl"))
    assert graph.follow(voltageLevel, "VoltageLevel.Substation").cimClass == "Substation"


def testReferenceAcrossTwoDocumentsResolves():
    graph = CimGraph()
    graph.add(rawObject("_t1", "Terminal", source="eq.xml", refs={"Terminal.TopologicalNode": "#_tn1"}))
    graph.add(rawObject("_tn1", "TopologicalNode", source="tp.xml"))
    terminal = graph.get(Identifier.fromRaw("_t1"))
    assert graph.follow(terminal, "Terminal.TopologicalNode").cimClass == "TopologicalNode"


def testUnresolvedReferenceIsReportedAndYieldsNone():
    diag = Diagnostics()
    graph = CimGraph(diagnostics=diag)
    graph.add(rawObject("_t1", "Terminal", refs={"Terminal.ConductingEquipment": "#_missing"}))
    terminal = graph.get(Identifier.fromRaw("_t1"))
    assert graph.follow(terminal, "Terminal.ConductingEquipment") is None
    assert diag.countByCode() == {"unresolvedReference": 1}
    assert diag.unresolvedReferenceCount == 1


def testMissingReferenceIsNotReportedAsUnresolved():
    diag = Diagnostics()
    graph = CimGraph(diagnostics=diag)
    graph.add(rawObject("_t1", "Terminal"))
    terminal = graph.get(Identifier.fromRaw("_t1"))
    assert graph.follow(terminal, "Terminal.ConductingEquipment") is None
    assert diag.issues == []


# --- cross-profile merging ---------------------------------------------------


def testSameObjectInTwoProfilesIsMergedIntoOneNode():
    graph = CimGraph()
    graph.add(rawObject("_sw1", "Switch", source="eq.xml", literals={"IdentifiedObject.name": "LS1"}))
    graph.add(rawObject("#_sw1", "Switch", source="ssh.xml", isAbout=True, literals={"Switch.open": "false"}))
    assert len(list(graph.objects)) == 1
    switch = graph.get(Identifier.fromRaw("_sw1"))
    assert switch.literal("IdentifiedObject.name") == "LS1"
    assert switch.literal("Switch.open") == "false"


def testMergedObjectRemembersEveryContributingDocument():
    graph = CimGraph()
    graph.add(rawObject("_sw1", "Switch", source="eq.xml"))
    graph.add(rawObject("#_sw1", "Switch", source="ssh.xml", isAbout=True))
    switch = graph.get(Identifier.fromRaw("_sw1"))
    assert [c.source.name for c in switch.contributions] == ["eq.xml", "ssh.xml"]


def testDefiningDeclarationWinsWhenTwoProfilesDisagreeOnALiteral():
    graph = CimGraph()
    graph.add(rawObject("#_sw1", "Switch", source="ssh.xml", isAbout=True, literals={"IdentifiedObject.name": "stale"}))
    graph.add(rawObject("_sw1", "Switch", source="eq.xml", order=1, literals={"IdentifiedObject.name": "current"}))
    assert graph.get(Identifier.fromRaw("_sw1")).literal("IdentifiedObject.name") == "current"


def testObjectKnownOnlyFromAnAboutDeclarationIsStillAvailable():
    graph = CimGraph()
    graph.add(rawObject("#_sw1", "Switch", source="ssh.xml", isAbout=True))
    assert graph.get(Identifier.fromRaw("_sw1")).cimClass == "Switch"


def testDuplicateDefiningDeclarationIsReportedAsAnError():
    diag = Diagnostics()
    graph = CimGraph(diagnostics=diag)
    graph.add(rawObject("_sub1", "Substation", source="eq.xml"))
    graph.add(rawObject("_sub1", "Substation", source="eq2.xml"))
    assert diag.countByCode() == {"duplicateIdentifier": 1}
    assert diag.errorCount == 1


def testConflictingClassAcrossProfilesIsReported():
    diag = Diagnostics()
    graph = CimGraph(diagnostics=diag)
    graph.add(rawObject("_x", "Breaker", source="eq.xml"))
    graph.add(rawObject("#_x", "Disconnector", source="ssh.xml", isAbout=True))
    assert "conflictingClass" in diag.countByCode()


# --- indexes -----------------------------------------------------------------


def testObjectsCanBeListedByCimClass():
    graph = CimGraph()
    graph.add(rawObject("_a", "Substation", order=0))
    graph.add(rawObject("_b", "Substation", order=1))
    graph.add(rawObject("_c", "VoltageLevel", order=2))
    assert [o.identifier.mrid for o in graph.byClass("Substation")] == ["a", "b"]


def testListingAnAbsentClassGivesAnEmptyList():
    assert CimGraph().byClass("Substation") == []


def testReverseIndexFindsObjectsPointingAtATarget():
    graph = CimGraph()
    graph.add(rawObject("_sub1", "Substation"))
    graph.add(rawObject("_vl1", "VoltageLevel", order=1, refs={"VoltageLevel.Substation": "#_sub1"}))
    graph.add(rawObject("_vl2", "VoltageLevel", order=2, refs={"VoltageLevel.Substation": "#_sub1"}))
    substation = graph.get(Identifier.fromRaw("_sub1"))
    assert [o.identifier.mrid for o in graph.referrers(substation, "VoltageLevel.Substation")] == ["vl1", "vl2"]


def testReverseIndexIsScopedToTheNamedProperty():
    graph = CimGraph()
    graph.add(rawObject("_n", "ConnectivityNode"))
    graph.add(rawObject("_t", "Terminal", order=1, refs={"Terminal.ConnectivityNode": "#_n"}))
    node = graph.get(Identifier.fromRaw("_n"))
    assert graph.referrers(node, "Terminal.TopologicalNode") == []


def testReverseIndexResolvesTargetsAddedAfterTheReferrer():
    graph = CimGraph()
    graph.add(rawObject("_vl1", "VoltageLevel", refs={"VoltageLevel.Substation": "#_sub1"}))
    graph.add(rawObject("_sub1", "Substation", order=1))
    substation = graph.get(Identifier.fromRaw("_sub1"))
    assert len(graph.referrers(substation, "VoltageLevel.Substation")) == 1


def testClassCountsSummariseTheModel():
    graph = CimGraph()
    graph.add(rawObject("_a", "Substation"))
    graph.add(rawObject("_b", "Terminal", order=1))
    graph.add(rawObject("_c", "Terminal", order=2))
    assert graph.classCounts() == {"Substation": 1, "Terminal": 2}


# --- reference integrity -----------------------------------------------------


def testIntegrityCheckFindsReferencesNobodyEverFollows():
    diag = Diagnostics()
    graph = CimGraph(diagnostics=diag)
    graph.add(rawObject("_t", "Terminal", refs={"Terminal.ConductingEquipment": "#_ghost"}))
    assert graph.verifyReferences() == 1
    assert diag.unresolvedReferenceCount == 1


def testIntegrityCheckPassesWhenEveryTargetExists():
    diag = Diagnostics()
    graph = CimGraph(diagnostics=diag)
    graph.add(rawObject("_eq", "ACLineSegment"))
    graph.add(rawObject("_t", "Terminal", order=1, refs={"Terminal.ConductingEquipment": "#_eq"}))
    assert graph.verifyReferences() == 0
    assert diag.issues == []


def testIntegrityCheckIgnoresEnumerationValues():
    diag = Diagnostics()
    graph = CimGraph(diagnostics=diag)
    graph.add(
        rawObject(
            "_e",
            "PowerTransformerEnd",
            refs={"TransformerEnd.connectionKind": f"{CIM16}WindingConnection.D"},
        )
    )
    assert graph.verifyReferences() == 0


def testIntegrityCheckReportsEachDanglingTargetOnlyOnce():
    diag = Diagnostics()
    graph = CimGraph(diagnostics=diag)
    graph.add(rawObject("_a", "Terminal", refs={"Terminal.ConductingEquipment": "#_ghost"}))
    graph.add(rawObject("_b", "Terminal", order=1, refs={"Terminal.ConductingEquipment": "#_ghost"}))
    assert graph.verifyReferences() == 2
    assert diag.unresolvedReferenceCount == 2


# --- identified object accessors ---------------------------------------------


def testNameAndShortNameAreExposedDirectly():
    graph = CimGraph()
    graph.add(
        rawObject(
            "_s",
            "Substation",
            literals={"IdentifiedObject.name": "Umspannwerk Nord", "IdentifiedObject.shortName": "UWN"},
        )
    )
    substation = graph.get(Identifier.fromRaw("_s"))
    assert substation.name == "Umspannwerk Nord"
    assert substation.shortName == "UWN"


def testMissingNameIsNoneRatherThanEmptyString():
    graph = CimGraph()
    graph.add(rawObject("_s", "Substation"))
    assert graph.get(Identifier.fromRaw("_s")).name is None


def testMridPrefersTheExplicitMridPropertyOverTheRdfId():
    graph = CimGraph()
    graph.add(rawObject("_s", "Substation", literals={"IdentifiedObject.mRID": "AAAA-BBBB"}))
    assert graph.get(Identifier.fromRaw("_s")).mrid == "AAAA-BBBB"


def testMridFallsBackToTheRdfIdWithoutItsUnderscore():
    graph = CimGraph()
    graph.add(rawObject("_0472a783-C766", "Substation"))
    assert graph.get(Identifier.fromRaw("_0472a783-c766")).mrid == "0472a783-C766"


def testFloatAccessorParsesNumericProperties():
    graph = CimGraph()
    graph.add(rawObject("_bv", "BaseVoltage", literals={"BaseVoltage.nominalVoltage": "380.0"}))
    assert graph.get(Identifier.fromRaw("_bv")).number("BaseVoltage.nominalVoltage") == 380.0


def testFloatAccessorReportsUnparseableNumbersAndReturnsNone():
    diag = Diagnostics()
    graph = CimGraph(diagnostics=diag)
    graph.add(rawObject("_bv", "BaseVoltage", literals={"BaseVoltage.nominalVoltage": "n/a"}))
    assert graph.get(Identifier.fromRaw("_bv")).number("BaseVoltage.nominalVoltage") is None
    assert "invalidNumber" in diag.countByCode()


def testIntAccessorParsesSequenceNumbers():
    graph = CimGraph()
    graph.add(rawObject("_t", "Terminal", literals={"ACDCTerminal.sequenceNumber": "2"}))
    assert graph.get(Identifier.fromRaw("_t")).integer("ACDCTerminal.sequenceNumber") == 2
