import zipfile

import cgmesFixtures as fx
import pytest

from cgmes2excel.inputs import InputNotFoundError, discoverDocuments, readDocument


def writeXml(tmpPath, name, body="<cim:Substation rdf:ID=\"_s\"/>"):
    return fx.writeDocument(tmpPath, name, body)


def testASingleFileIsDiscovered(tmp_path):
    path = writeXml(tmp_path, "eq.xml")
    assert [source.name for source in discoverDocuments([path])] == ["eq.xml"]


def testADirectoryYieldsItsXmlFilesInSortedOrder(tmp_path):
    writeXml(tmp_path, "b_TP.xml")
    writeXml(tmp_path, "a_EQ.xml")
    assert [source.name for source in discoverDocuments([tmp_path])] == ["a_EQ.xml", "b_TP.xml"]


def testNonXmlFilesInADirectoryAreIgnored(tmp_path):
    writeXml(tmp_path, "eq.xml")
    (tmp_path / "readme.txt").write_text("not a profile", encoding="utf-8")
    assert [source.name for source in discoverDocuments([tmp_path])] == ["eq.xml"]


def testNestedDirectoriesAreSearched(tmp_path):
    nested = tmp_path / "export" / "profiles"
    nested.mkdir(parents=True)
    writeXml(nested, "eq.xml")
    assert [source.name for source in discoverDocuments([tmp_path])] == ["eq.xml"]


def testZipArchivesAreExpandedIntoTheirMembers(tmp_path):
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("grid_EQ.xml", fx.rdfDocument(fx.sampleEquipment(), profile="EQ"))
        zf.writestr("grid_TP.xml", fx.rdfDocument(fx.sampleTopology(), profile="TP"))
    assert [source.name for source in discoverDocuments([archive])] == ["grid_EQ.xml", "grid_TP.xml"]


def testZipMembersThatAreNotXmlAreIgnored(tmp_path):
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("grid_EQ.xml", fx.rdfDocument("", profile="EQ"))
        zf.writestr("notes.txt", "hello")
    assert [source.name for source in discoverDocuments([archive])] == ["grid_EQ.xml"]


def testZipMemberDisplayPathNamesItsArchive(tmp_path):
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("grid_EQ.xml", fx.rdfDocument("", profile="EQ"))
    (source,) = discoverDocuments([archive])
    assert "export.zip" in str(source.displayPath)
    assert source.displayPath.name == "grid_EQ.xml"


def testAZipInsideADirectoryIsAlsoExpanded(tmp_path):
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("grid_EQ.xml", fx.rdfDocument("", profile="EQ"))
    assert [source.name for source in discoverDocuments([tmp_path])] == ["grid_EQ.xml"]


def testDuplicateInputsAreDiscoveredOnlyOnce(tmp_path):
    path = writeXml(tmp_path, "eq.xml")
    assert len(discoverDocuments([path, path, tmp_path])) == 1


def testAMissingPathIsRejected(tmp_path):
    with pytest.raises(InputNotFoundError):
        discoverDocuments([tmp_path / "nope.xml"])


def testAnEmptyDirectoryYieldsNothing(tmp_path):
    assert discoverDocuments([tmp_path]) == []


def testDocumentsFromFilesCanBeRead(tmp_path):
    path = fx.writeDocument(tmp_path, "eq.xml", fx.sampleEquipment())
    (source,) = discoverDocuments([path])
    objects = list(readDocument(source))
    assert any(obj.cimClass == "Substation" for obj in objects)


def testDocumentsFromZipMembersCanBeRead(tmp_path):
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("grid_EQ.xml", fx.rdfDocument(fx.sampleEquipment(), profile="EQ"))
    (source,) = discoverDocuments([archive])
    objects = list(readDocument(source))
    assert any(obj.cimClass == "Substation" for obj in objects)


def testObjectsFromAZipMemberCarryTheMemberAsTheirSource(tmp_path):
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("grid_EQ.xml", fx.rdfDocument(fx.sampleEquipment(), profile="EQ"))
    (source,) = discoverDocuments([archive])
    objects = list(readDocument(source))
    assert objects[0].source.name == "grid_EQ.xml"
