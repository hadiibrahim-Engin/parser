"""XML namespace identity for CIM/CGMES documents.

Semantic identity comes from the namespace URI, never from the document's
prefix choice, so ``cim:``, ``c:`` or any other prefix parse identically.
"""

from __future__ import annotations

RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
MD_NS = "http://iec.ch/TC57/61970-552/ModelDescription/1#"

CIM16_NS = "http://iec.ch/TC57/2013/CIM-schema-cim16#"
CIM17_NS = "http://iec.ch/TC57/2013/CIM-schema-cim17#"
CIM100_NS = "http://iec.ch/TC57/CIM100#"

KNOWN_CIM_NAMESPACES = frozenset({CIM16_NS, CIM17_NS, CIM100_NS})

RDF_ID = f"{{{RDF_NS}}}ID"
RDF_ABOUT = f"{{{RDF_NS}}}about"
RDF_RESOURCE = f"{{{RDF_NS}}}resource"


def splitTag(tag: str) -> tuple[str, str]:
    """Split an ElementTree ``{namespace}local`` tag into its two parts."""
    if tag.startswith("{"):
        namespace, _, local = tag[1:].partition("}")
        return namespace, local
    return "", tag


def isCimNamespace(namespace: str) -> bool:
    """Whether a namespace URI denotes a CIM schema of any supported version."""
    if namespace in KNOWN_CIM_NAMESPACES:
        return True
    return "CIM-schema-cim" in namespace or "/CIM100" in namespace


def cimVersionLabel(namespace: str) -> str:
    """Human-readable CIM schema version for a namespace URI."""
    if namespace == CIM100_NS or "/CIM100" in namespace:
        return "CIM100 (CGMES 3.0)"
    if namespace == CIM16_NS:
        return "CIM16 (CGMES 2.4.15)"
    if namespace == CIM17_NS:
        return "CIM17"
    return namespace
