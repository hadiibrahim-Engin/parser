"""Helpers for assembling synthetic CGMES exports in tests."""

from __future__ import annotations

from pathlib import Path

from cgmes2excel.cgmes.graph import CimGraph
from cgmes2excel.cgmes.namespaces import MD_NS, RDF_NS
from cgmes2excel.cgmes.reader import readRdfXml
from cgmes2excel.diagnostics import Diagnostics

CIM16 = "http://iec.ch/TC57/2013/CIM-schema-cim16#"

PROFILE_URIS = {
    "EQ": "http://entsoe.eu/CIM/EquipmentCore/3/1",
    "SSH": "http://entsoe.eu/CIM/SteadyStateHypothesis/1/1",
    "TP": "http://entsoe.eu/CIM/Topology/4/1",
    "SV": "http://entsoe.eu/CIM/StateVariables/4/1",
    "GL": "http://entsoe.eu/CIM/GeographicalLocation/2/1",
}


def rdfDocument(body: str, profile: str | None = None, cim: str = CIM16, modelId: str = "model") -> str:
    header = ""
    if profile is not None:
        header = (
            f'<md:FullModel rdf:about="urn:uuid:{modelId}">'
            f"<md:Model.scenarioTime>2024-06-01T10:00:00Z</md:Model.scenarioTime>"
            f"<md:Model.created>2024-06-02T08:30:00Z</md:Model.created>"
            f"<md:Model.profile>{PROFILE_URIS[profile]}</md:Model.profile>"
            f"</md:FullModel>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<rdf:RDF xmlns:rdf="{RDF_NS}" xmlns:cim="{cim}" xmlns:md="{MD_NS}">'
        f"{header}{body}</rdf:RDF>"
    )


def writeDocument(tmpPath: Path, name: str, body: str, profile: str | None = None, **kw) -> Path:
    path = tmpPath / name
    path.write_text(rdfDocument(body, profile=profile, **kw), encoding="utf-8")
    return path


def loadGraph(paths: list[Path], diagnostics: Diagnostics | None = None) -> CimGraph:
    graph = CimGraph(diagnostics=diagnostics or Diagnostics())
    for path in paths:
        for raw in readRdfXml(path):
            graph.add(raw)
    return graph


def graphFrom(tmpPath: Path, documents: dict[str, str], diagnostics: Diagnostics | None = None) -> CimGraph:
    """Build a graph from ``{filename: xml body}``, loaded in sorted filename order."""
    paths = [writeDocument(tmpPath, name, body) for name, body in documents.items()]
    return loadGraph(sorted(paths), diagnostics)


# --- element builders --------------------------------------------------------


def obj(cimClass: str, rdfId: str, *children: str, about: bool = False) -> str:
    attribute = "rdf:about" if about else "rdf:ID"
    value = f"#_{rdfId}" if about else f"_{rdfId}"
    return f'<cim:{cimClass} {attribute}="{value}">{"".join(children)}</cim:{cimClass}>'


def prop(name: str, value: str) -> str:
    return f"<cim:{name}>{value}</cim:{name}>"


def ref(name: str, target: str) -> str:
    return f'<cim:{name} rdf:resource="#_{target}"/>'


def named(name: str, shortName: str | None = None) -> str:
    parts = [prop("IdentifiedObject.name", name)]
    if shortName is not None:
        parts.append(prop("IdentifiedObject.shortName", shortName))
    return "".join(parts)


# --- a small two-station grid used across the semantic tests ------------------


def sampleEquipment() -> str:
    return "".join(
        [
            obj("GeographicalRegion", "GR1", named("Region Nord")),
            obj("SubGeographicalRegion", "SGR1", named("Küste"), ref("SubGeographicalRegion.Region", "GR1")),
            obj("BaseVoltage", "BV380", named("380 kV"), prop("BaseVoltage.nominalVoltage", "380")),
            obj("BaseVoltage", "BV110", named("110 kV"), prop("BaseVoltage.nominalVoltage", "110")),
            obj(
                "Substation",
                "SUBA",
                named("Umspannwerk Alpha", "UWA"),
                ref("Substation.Region", "SGR1"),
            ),
            obj(
                "Substation",
                "SUBB",
                named("Umspannwerk Beta", "UWB"),
                ref("Substation.Region", "SGR1"),
            ),
            obj(
                "VoltageLevel",
                "VLA380",
                named("A 380kV"),
                ref("VoltageLevel.Substation", "SUBA"),
                ref("VoltageLevel.BaseVoltage", "BV380"),
            ),
            obj(
                "VoltageLevel",
                "VLA110",
                named("A 110kV"),
                ref("VoltageLevel.Substation", "SUBA"),
                ref("VoltageLevel.BaseVoltage", "BV110"),
            ),
            obj(
                "VoltageLevel",
                "VLB380",
                named("B 380kV"),
                ref("VoltageLevel.Substation", "SUBB"),
                ref("VoltageLevel.BaseVoltage", "BV380"),
            ),
            obj("ConnectivityNode", "CNA380", named("CN A 380"), ref("ConnectivityNode.ConnectivityNodeContainer", "VLA380")),
            obj("ConnectivityNode", "CNA110", named("CN A 110"), ref("ConnectivityNode.ConnectivityNodeContainer", "VLA110")),
            obj("ConnectivityNode", "CNB380", named("CN B 380"), ref("ConnectivityNode.ConnectivityNodeContainer", "VLB380")),
            obj("Line", "LINEC", named("Stromkreis Alpha-Beta", "SK-AB"), ref("Line.Region", "SGR1")),
            obj(
                "ACLineSegment",
                "LINE1",
                named("Leitung Alpha-Beta", "L-AB"),
                ref("Equipment.EquipmentContainer", "LINEC"),
                ref("ConductingEquipment.BaseVoltage", "BV380"),
            ),
            obj(
                "Terminal",
                "TL1",
                named("Leitung T1"),
                prop("ACDCTerminal.sequenceNumber", "1"),
                ref("Terminal.ConductingEquipment", "LINE1"),
                ref("Terminal.ConnectivityNode", "CNA380"),
            ),
            obj(
                "Terminal",
                "TL2",
                named("Leitung T2"),
                prop("ACDCTerminal.sequenceNumber", "2"),
                ref("Terminal.ConductingEquipment", "LINE1"),
                ref("Terminal.ConnectivityNode", "CNB380"),
            ),
            obj(
                "PowerTransformer",
                "TRA",
                named("Transformator A", "TR-A"),
                ref("Equipment.EquipmentContainer", "SUBA"),
            ),
            obj(
                "Terminal",
                "TT1",
                named("Trafo T1"),
                prop("ACDCTerminal.sequenceNumber", "1"),
                ref("Terminal.ConductingEquipment", "TRA"),
                ref("Terminal.ConnectivityNode", "CNA380"),
            ),
            obj(
                "Terminal",
                "TT2",
                named("Trafo T2"),
                prop("ACDCTerminal.sequenceNumber", "2"),
                ref("Terminal.ConductingEquipment", "TRA"),
                ref("Terminal.ConnectivityNode", "CNA110"),
            ),
            obj(
                "PowerTransformerEnd",
                "TE1",
                named("Ende 1"),
                prop("TransformerEnd.endNumber", "1"),
                ref("PowerTransformerEnd.PowerTransformer", "TRA"),
                ref("TransformerEnd.Terminal", "TT1"),
                ref("TransformerEnd.BaseVoltage", "BV380"),
            ),
            obj(
                "PowerTransformerEnd",
                "TE2",
                named("Ende 2"),
                prop("TransformerEnd.endNumber", "2"),
                ref("PowerTransformerEnd.PowerTransformer", "TRA"),
                ref("TransformerEnd.Terminal", "TT2"),
                ref("TransformerEnd.BaseVoltage", "BV110"),
            ),
        ]
    )


def sampleTopology() -> str:
    return "".join(
        [
            obj("TopologicalNode", "TNA380", named("Knoten A 380"), ref("TopologicalNode.ConnectivityNodeContainer", "VLA380"), ref("TopologicalNode.BaseVoltage", "BV380")),
            obj("TopologicalNode", "TNA110", named("Knoten A 110"), ref("TopologicalNode.ConnectivityNodeContainer", "VLA110"), ref("TopologicalNode.BaseVoltage", "BV110")),
            obj("TopologicalNode", "TNB380", named("Knoten B 380"), ref("TopologicalNode.ConnectivityNodeContainer", "VLB380"), ref("TopologicalNode.BaseVoltage", "BV380")),
            obj("Terminal", "TL1", ref("Terminal.TopologicalNode", "TNA380"), about=True),
            obj("Terminal", "TL2", ref("Terminal.TopologicalNode", "TNB380"), about=True),
            obj("Terminal", "TT1", ref("Terminal.TopologicalNode", "TNA380"), about=True),
            obj("Terminal", "TT2", ref("Terminal.TopologicalNode", "TNA110"), about=True),
        ]
    )


def sampleSteadyState() -> str:
    return "".join(
        [
            obj("Terminal", "TL1", prop("ACDCTerminal.connected", "true"), about=True),
            obj("Terminal", "TL2", prop("ACDCTerminal.connected", "true"), about=True),
        ]
    )


def sampleGeography() -> str:
    return "".join(
        [
            obj("CoordinateSystem", "CRS1", named("WGS84"), prop("CoordinateSystem.crsUrn", "urn:ogc:def:crs:EPSG::4326")),
            obj(
                "Location",
                "LOCA",
                named("Standort Alpha"),
                ref("Location.CoordinateSystem", "CRS1"),
                ref("Location.PowerSystemResources", "SUBA"),
            ),
            obj(
                "Location",
                "LOCB",
                named("Standort Beta"),
                ref("Location.CoordinateSystem", "CRS1"),
                ref("Location.PowerSystemResources", "SUBB"),
            ),
            obj(
                "PositionPoint",
                "PPA",
                prop("PositionPoint.sequenceNumber", "1"),
                prop("PositionPoint.xPosition", "9.993682"),
                prop("PositionPoint.yPosition", "53.551086"),
                ref("PositionPoint.Location", "LOCA"),
            ),
            obj(
                "PositionPoint",
                "PPB",
                prop("PositionPoint.sequenceNumber", "1"),
                prop("PositionPoint.xPosition", "10.686389"),
                prop("PositionPoint.yPosition", "53.866667"),
                ref("PositionPoint.Location", "LOCB"),
            ),
        ]
    )


def sampleStateVariables() -> str:
    return "".join(
        [
            obj("SvVoltage", "SV1", prop("SvVoltage.v", "398.2"), prop("SvVoltage.angle", "0.0"), ref("SvVoltage.TopologicalNode", "TNA380")),
        ]
    )


def sampleExport(tmpPath: Path) -> list[Path]:
    """Write a five-profile export of a two-station grid and return its paths."""
    return [
        writeDocument(tmpPath, "grid_EQ.xml", sampleEquipment(), profile="EQ"),
        writeDocument(tmpPath, "grid_SSH.xml", sampleSteadyState(), profile="SSH"),
        writeDocument(tmpPath, "grid_TP.xml", sampleTopology(), profile="TP"),
        writeDocument(tmpPath, "grid_SV.xml", sampleStateVariables(), profile="SV"),
        writeDocument(tmpPath, "grid_GL.xml", sampleGeography(), profile="GL"),
    ]


def sampleGraph(tmpPath: Path, diagnostics: Diagnostics | None = None) -> CimGraph:
    return loadGraph(sampleExport(tmpPath), diagnostics)
