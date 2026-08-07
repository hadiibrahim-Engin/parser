from cgmes2excel.cgmes.identifiers import Identifier, normalizeId


def testPlainRdfIdNormalizesToItself():
    assert normalizeId("_0472a783-c766-11e1-8775-005056c00008") == "0472a783-c766-11e1-8775-005056c00008"


def testRdfResourceFragmentReferenceMatchesRdfId():
    assert normalizeId("#_0472a783-c766-11e1") == normalizeId("_0472a783-c766-11e1")


def testUrnUuidReferenceMatchesRdfId():
    assert normalizeId("urn:uuid:0472a783-c766-11e1") == normalizeId("_0472a783-c766-11e1")


def testAbsoluteUrlReferenceUsesFragment():
    assert normalizeId("http://example.com/model.xml#_ABC-123") == normalizeId("_abc-123")


def testNormalizationIsCaseInsensitive():
    assert normalizeId("_AbC") == normalizeId("_aBc")


def testEmptyReferenceNormalizesToEmptyString():
    assert normalizeId("") == ""
    assert normalizeId("   ") == ""
    assert normalizeId(None) == ""


def testIdentifierPreservesOriginalRawValue():
    ident = Identifier.fromRaw("#_0472a783-C766-11e1")
    assert ident.raw == "#_0472a783-C766-11e1"
    assert ident.key == "0472a783-c766-11e1"


def testIdentifierMridStripsOnlyLeadingUnderscoreAndKeepsCase():
    assert Identifier.fromRaw("_0472a783-C766-11e1").mrid == "0472a783-C766-11e1"


def testIdentifiersWithSameKeyAreEqualAndHashAlike():
    a = Identifier.fromRaw("#_ABC")
    b = Identifier.fromRaw("urn:uuid:abc")
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1
