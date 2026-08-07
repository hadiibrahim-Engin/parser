from pathlib import Path

from cgmes2excel.cgmes.identifiers import Identifier
from cgmes2excel.cgmes.profiles import DetectionSource, Profile, ProfileEvidence, detectProfile
from cgmes2excel.cgmes.reader import RawObject
from cgmes2excel.diagnostics import Diagnostics

CIM16 = "http://iec.ch/TC57/2013/CIM-schema-cim16#"
MD = "http://iec.ch/TC57/61970-552/ModelDescription/1#"


def raw(cimClass, namespace=CIM16, rdfId="_x", isAbout=False, literals=None, refs=None):
    obj = RawObject(
        identifier=Identifier.fromRaw(rdfId),
        cimClass=cimClass,
        classNamespace=namespace,
        source=Path("doc.xml"),
        documentOrder=0,
        isAbout=isAbout,
    )
    for name, values in (literals or {}).items():
        for value in values if isinstance(values, list) else [values]:
            obj.addLiteral(name, value)
    for name, value in (refs or {}).items():
        obj.addReference(name, Identifier.fromRaw(value))
    return obj


def fullModel(*profileUris):
    return raw("FullModel", namespace=MD, rdfId="urn:uuid:m1", literals={"Model.profile": list(profileUris)})


def detect(objects, path="doc.xml", diagnostics=None):
    evidence = ProfileEvidence()
    for obj in objects:
        evidence.note(obj)
    return detectProfile(Path(path), evidence, diagnostics or Diagnostics())


# --- model header (preferred) ------------------------------------------------


def testEquipmentProfileIsDetectedFromTheModelHeader():
    result = detect([fullModel("http://entsoe.eu/CIM/EquipmentCore/3/1")])
    assert result.profile is Profile.EQ
    assert result.detectedBy is DetectionSource.MODEL_HEADER


def testSteadyStateHypothesisProfileIsDetectedFromTheModelHeader():
    assert detect([fullModel("http://entsoe.eu/CIM/SteadyStateHypothesis/1/1")]).profile is Profile.SSH


def testTopologyProfileIsDetectedFromTheModelHeader():
    assert detect([fullModel("http://entsoe.eu/CIM/Topology/4/1")]).profile is Profile.TP


def testStateVariablesProfileIsDetectedFromTheModelHeader():
    assert detect([fullModel("http://entsoe.eu/CIM/StateVariables/4/1")]).profile is Profile.SV


def testGeographicalLocationProfileIsDetectedFromTheModelHeader():
    assert detect([fullModel("http://entsoe.eu/CIM/GeographicalLocation/2/1")]).profile is Profile.GL


def testCgmesThreeProfileUrisAreRecognised():
    assert detect([fullModel("http://iec.ch/TC57/ns/CIM/CoreEquipment-EU/3.0")]).profile is Profile.EQ
    assert detect([fullModel("http://iec.ch/TC57/ns/CIM/SteadyStateHypothesis-EU/3.0")]).profile is Profile.SSH
    assert detect([fullModel("http://iec.ch/TC57/ns/CIM/Topology-EU/3.0")]).profile is Profile.TP
    assert detect([fullModel("http://iec.ch/TC57/ns/CIM/StateVariables-EU/3.0")]).profile is Profile.SV
    assert detect([fullModel("http://iec.ch/TC57/ns/CIM/GeographicalLocation-EU/3.0")]).profile is Profile.GL


def testBoundaryProfilesAreDistinguishedFromTheirCoreProfiles():
    assert detect([fullModel("http://entsoe.eu/CIM/EquipmentBoundary/3/1")]).profile is Profile.EQBD
    assert detect([fullModel("http://entsoe.eu/CIM/TopologyBoundary/3/1")]).profile is Profile.TPBD


def testSeveralEquipmentSubProfilesStillResolveToEquipment():
    result = detect(
        [fullModel("http://entsoe.eu/CIM/EquipmentCore/3/1", "http://entsoe.eu/CIM/EquipmentOperation/3/1")]
    )
    assert result.profile is Profile.EQ
    assert len(result.profileUris) == 2


def testModelHeaderIsPreferredOverAMisleadingFilename():
    result = detect([fullModel("http://entsoe.eu/CIM/Topology/4/1")], path="something_EQ.xml")
    assert result.profile is Profile.TP


def testModelIdentifierIsCapturedFromTheHeader():
    assert detect([fullModel("http://entsoe.eu/CIM/Topology/4/1")]).modelId == "m1"


# --- content heuristics (fallback) -------------------------------------------


def testTopologyIsInferredFromTopologicalNodesWhenNoHeaderExists():
    result = detect([raw("TopologicalNode"), raw("TopologicalNode")], path="unnamed.xml")
    assert result.profile is Profile.TP
    assert result.detectedBy is DetectionSource.CONTENT


def testStateVariablesAreInferredFromSvClasses():
    assert detect([raw("SvVoltage"), raw("SvPowerFlow")], path="unnamed.xml").profile is Profile.SV


def testGeographicalLocationIsInferredFromPositionPoints():
    assert detect([raw("PositionPoint"), raw("Location")], path="unnamed.xml").profile is Profile.GL


def testEquipmentIsInferredFromSubstationsAndVoltageLevels():
    assert detect([raw("Substation"), raw("VoltageLevel"), raw("Terminal")], path="unnamed.xml").profile is Profile.EQ


def testSteadyStateHypothesisIsInferredFromUpdateOnlyDescriptions():
    objects = [
        raw("Switch", rdfId="#_a", isAbout=True, literals={"Switch.open": "false"}),
        raw("EnergyConsumer", rdfId="#_b", isAbout=True, literals={"EnergyConsumer.p": "12.5"}),
    ]
    assert detect(objects, path="unnamed.xml").profile is Profile.SSH


def testContentDetectionIgnoresTheFullModelObjectItself():
    result = detect([raw("FullModel", namespace=MD, rdfId="urn:uuid:m"), raw("PositionPoint")], path="unnamed.xml")
    assert result.profile is Profile.GL


# --- filename hints (last resort) --------------------------------------------


def testFilenameIsUsedOnlyWhenNothingElseIdentifiesTheProfile():
    result = detect([], path="20240101_SomeGrid_SSH.xml")
    assert result.profile is Profile.SSH
    assert result.detectedBy is DetectionSource.FILENAME


def testFilenameHintToleratesLowercaseAndSeparators():
    assert detect([], path="model-tp.xml").profile is Profile.TP
    assert detect([], path="grid_gl_v2.xml").profile is Profile.GL


def testCompletelyUnidentifiableDocumentIsReported():
    diag = Diagnostics()
    result = detect([], path="data.xml", diagnostics=diag)
    assert result.profile is Profile.UNKNOWN
    assert result.detectedBy is DetectionSource.NONE
    assert "unknownProfile" in diag.countByCode()


# --- cim version -------------------------------------------------------------


def testCimNamespaceOfTheDocumentIsCaptured():
    assert detect([raw("Substation")], path="eq.xml").cimNamespace == CIM16


def testCim100NamespaceIsCaptured():
    cim100 = "http://iec.ch/TC57/CIM100#"
    assert detect([raw("Substation", namespace=cim100)], path="eq.xml").cimNamespace == cim100
