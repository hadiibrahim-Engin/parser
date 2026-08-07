import pytest

from cgmes2excel.cgmes.namespaces import RDF_NS, isCimNamespace, splitTag
from cgmes2excel.cgmes.reader import MalformedDocumentError, readRdfXml

CIM16 = "http://iec.ch/TC57/2013/CIM-schema-cim16#"
CIM100 = "http://iec.ch/TC57/CIM100#"
MD = "http://iec.ch/TC57/61970-552/ModelDescription/1#"


def wrap(body: str, cim: str = CIM16, prefix: str = "cim") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<rdf:RDF xmlns:rdf="{RDF_NS}" xmlns:{prefix}="{cim}" xmlns:md="{MD}">'
        f"{body}</rdf:RDF>"
    )


def writeDoc(tmpPath, name, body, **kw):
    path = tmpPath / name
    path.write_text(wrap(body, **kw), encoding="utf-8")
    return path


# --- namespace helpers -------------------------------------------------------


def testSplitTagSeparatesNamespaceAndLocalName():
    assert splitTag(f"{{{CIM16}}}Substation") == (CIM16, "Substation")


def testSplitTagHandlesTagWithoutNamespace():
    assert splitTag("Substation") == ("", "Substation")


def testCim16AndCim100NamespacesAreRecognisedAsCim():
    assert isCimNamespace(CIM16)
    assert isCimNamespace(CIM100)


def testRdfNamespaceIsNotACimNamespace():
    assert not isCimNamespace(RDF_NS)


# --- parsing -----------------------------------------------------------------


def testReadsObjectClassAndIdentifierFromRdfId(tmp_path):
    path = writeDoc(tmp_path, "eq.xml", '<cim:Substation rdf:ID="_sub1"/>')
    objects = list(readRdfXml(path))
    assert len(objects) == 1
    assert objects[0].cimClass == "Substation"
    assert objects[0].identifier.key == "sub1"


def testReadsIdentifierFromRdfAbout(tmp_path):
    path = writeDoc(tmp_path, "ssh.xml", '<cim:Switch rdf:about="#_sw1"/>')
    (obj,) = list(readRdfXml(path))
    assert obj.identifier.key == "sw1"
    assert obj.isAbout is True


def testRdfIdObjectIsNotMarkedAsAbout(tmp_path):
    path = writeDoc(tmp_path, "eq.xml", '<cim:Switch rdf:ID="_sw1"/>')
    (obj,) = list(readRdfXml(path))
    assert obj.isAbout is False


def testReadsLiteralPropertyValue(tmp_path):
    body = '<cim:Substation rdf:ID="_s"><cim:IdentifiedObject.name>Nord</cim:IdentifiedObject.name></cim:Substation>'
    path = writeDoc(tmp_path, "eq.xml", body)
    (obj,) = list(readRdfXml(path))
    assert obj.literal("IdentifiedObject.name") == "Nord"


def testMissingLiteralPropertyReturnsNone(tmp_path):
    path = writeDoc(tmp_path, "eq.xml", '<cim:Substation rdf:ID="_s"/>')
    (obj,) = list(readRdfXml(path))
    assert obj.literal("IdentifiedObject.name") is None


def testReadsReferencePropertyAsIdentifier(tmp_path):
    body = '<cim:VoltageLevel rdf:ID="_vl"><cim:VoltageLevel.Substation rdf:resource="#_sub1"/></cim:VoltageLevel>'
    path = writeDoc(tmp_path, "eq.xml", body)
    (obj,) = list(readRdfXml(path))
    assert obj.reference("VoltageLevel.Substation").key == "sub1"


def testRepeatedPropertyKeepsEveryValueInOrder(tmp_path):
    body = (
        '<md:FullModel rdf:about="urn:uuid:m1">'
        "<md:Model.profile>http://a/EquipmentCore/3</md:Model.profile>"
        "<md:Model.profile>http://a/EquipmentOperation/3</md:Model.profile>"
        "</md:FullModel>"
    )
    path = writeDoc(tmp_path, "eq.xml", body)
    (obj,) = list(readRdfXml(path))
    assert obj.literals("Model.profile") == [
        "http://a/EquipmentCore/3",
        "http://a/EquipmentOperation/3",
    ]


def testPropertyNamespaceIsPreservedForNonCimExtensions(tmp_path):
    body = '<md:FullModel rdf:about="urn:uuid:m1"><md:Model.scenarioTime>2024-01-01T00:00:00Z</md:Model.scenarioTime></md:FullModel>'
    path = writeDoc(tmp_path, "eq.xml", body)
    (obj,) = list(readRdfXml(path))
    assert obj.classNamespace == MD
    assert obj.literal("Model.scenarioTime") == "2024-01-01T00:00:00Z"


def testParsingIsIndependentOfXmlNamespacePrefix(tmp_path):
    path = writeDoc(tmp_path, "eq.xml", '<c:Substation rdf:ID="_s"/>', prefix="c")
    (obj,) = list(readRdfXml(path))
    assert obj.cimClass == "Substation"
    assert obj.classNamespace == CIM16


def testCim100DocumentsAreParsedTheSameWay(tmp_path):
    path = writeDoc(tmp_path, "eq.xml", '<cim:Substation rdf:ID="_s"/>', cim=CIM100)
    (obj,) = list(readRdfXml(path))
    assert obj.cimClass == "Substation"
    assert obj.classNamespace == CIM100


def testEnumReferenceExposesItsFragmentAsValue(tmp_path):
    body = (
        '<cim:PowerTransformerEnd rdf:ID="_e">'
        f'<cim:TransformerEnd.connectionKind rdf:resource="{CIM16}WindingConnection.D"/>'
        "</cim:PowerTransformerEnd>"
    )
    path = writeDoc(tmp_path, "eq.xml", body)
    (obj,) = list(readRdfXml(path))
    assert obj.enum("TransformerEnd.connectionKind") == "D"


def testDocumentOrderIsRecordedForDeterministicTiebreaks(tmp_path):
    path = writeDoc(tmp_path, "eq.xml", '<cim:Terminal rdf:ID="_t1"/><cim:Terminal rdf:ID="_t2"/>')
    a, b = list(readRdfXml(path))
    assert (a.documentOrder, b.documentOrder) == (0, 1)


def testSourceDocumentPathIsRecorded(tmp_path):
    path = writeDoc(tmp_path, "eq.xml", '<cim:Substation rdf:ID="_s"/>')
    (obj,) = list(readRdfXml(path))
    assert obj.source == path


def testWhitespaceAroundLiteralValuesIsStripped(tmp_path):
    body = '<cim:Substation rdf:ID="_s"><cim:IdentifiedObject.name>\n  Nord \n</cim:IdentifiedObject.name></cim:Substation>'
    path = writeDoc(tmp_path, "eq.xml", body)
    (obj,) = list(readRdfXml(path))
    assert obj.literal("IdentifiedObject.name") == "Nord"


def testUnicodeAndSpecialCharactersSurviveParsing(tmp_path):
    body = '<cim:Substation rdf:ID="_s"><cim:IdentifiedObject.name>Umspannwerk Süd &amp; Ost</cim:IdentifiedObject.name></cim:Substation>'
    path = writeDoc(tmp_path, "eq.xml", body)
    (obj,) = list(readRdfXml(path))
    assert obj.literal("IdentifiedObject.name") == "Umspannwerk Süd & Ost"


def testObjectWithoutAnyIdentifierIsSkipped(tmp_path):
    path = writeDoc(tmp_path, "eq.xml", "<cim:Substation/>")
    assert list(readRdfXml(path)) == []


def testMalformedXmlRaisesADedicatedError(tmp_path):
    path = tmp_path / "broken.xml"
    path.write_text('<rdf:RDF xmlns:rdf="x"><unclosed>', encoding="utf-8")
    with pytest.raises(MalformedDocumentError):
        list(readRdfXml(path))
