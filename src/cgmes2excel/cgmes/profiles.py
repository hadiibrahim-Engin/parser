"""CGMES profile identification for a single document.

Three ranked strategies: the ``md:FullModel`` header is authoritative, the set
of classes and properties actually present is the fallback, and the filename is
only a last resort. Filenames in real exports are frequently misleading.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from cgmes2excel.cgmes.namespaces import isCimNamespace
from cgmes2excel.cgmes.reader import RawObject
from cgmes2excel.diagnostics import Diagnostics


class Profile(Enum):
    EQ = "EQ"
    SSH = "SSH"
    TP = "TP"
    SV = "SV"
    GL = "GL"
    DL = "DL"
    DY = "DY"
    EQBD = "EQBD"
    TPBD = "TPBD"
    UNKNOWN = "UNKNOWN"


class DetectionSource(Enum):
    MODEL_HEADER = "modelHeader"
    CONTENT = "content"
    FILENAME = "filename"
    NONE = "none"


# Ordered: the first matching token wins, so boundary profiles are tested
# before the core profiles whose names they contain.
_PROFILE_URI_TOKENS: tuple[tuple[str, Profile], ...] = (
    ("equipmentboundary", Profile.EQBD),
    ("boundaryequipment", Profile.EQBD),
    ("topologyboundary", Profile.TPBD),
    ("boundarytopology", Profile.TPBD),
    ("steadystatehypothesis", Profile.SSH),
    ("statevariables", Profile.SV),
    ("geographicallocation", Profile.GL),
    ("diagramlayout", Profile.DL),
    ("dynamics", Profile.DY),
    ("topology", Profile.TP),
    ("equipment", Profile.EQ),
    ("operation", Profile.EQ),
    ("shortcircuit", Profile.EQ),
)

_MARKER_CLASSES: dict[str, Profile] = {
    "PositionPoint": Profile.GL,
    "CoordinateSystem": Profile.GL,
    "Location": Profile.GL,
    "SvVoltage": Profile.SV,
    "SvPowerFlow": Profile.SV,
    "SvTapStep": Profile.SV,
    "SvShuntCompensatorSections": Profile.SV,
    "SvInjection": Profile.SV,
    "SvStatus": Profile.SV,
    "TopologicalNode": Profile.TP,
    "TopologicalIsland": Profile.TP,
    "Substation": Profile.EQ,
    "VoltageLevel": Profile.EQ,
    "BaseVoltage": Profile.EQ,
    "Bay": Profile.EQ,
    "ACLineSegment": Profile.EQ,
    "PowerTransformer": Profile.EQ,
    "ConnectivityNode": Profile.EQ,
    "GeographicalRegion": Profile.EQ,
    "SubGeographicalRegion": Profile.EQ,
}

_SSH_PROPERTIES = frozenset(
    {
        "Switch.open",
        "EnergyConsumer.p",
        "EnergyConsumer.q",
        "RotatingMachine.p",
        "RotatingMachine.q",
        "RegulatingControl.targetValue",
        "RegulatingCondEq.controlEnabled",
        "TapChanger.step",
        "TapChanger.controlEnabled",
        "ACDCTerminal.connected",
        "Terminal.connected",
        "ShuntCompensator.sections",
        "EquivalentInjection.p",
        "ConductingEquipment.inService",
    }
)

_FILENAME_TOKENS: tuple[tuple[str, Profile], ...] = (
    ("eqbd", Profile.EQBD),
    ("tpbd", Profile.TPBD),
    ("ssh", Profile.SSH),
    ("sv", Profile.SV),
    ("tp", Profile.TP),
    ("gl", Profile.GL),
    ("dl", Profile.DL),
    ("dy", Profile.DY),
    ("eq", Profile.EQ),
)

_MODEL_CLASS = "FullModel"


@dataclass(slots=True)
class ProfileEvidence:
    """Accumulates what a document contains while it is being streamed."""

    classCounts: Counter[str] = field(default_factory=Counter)
    profileUris: list[str] = field(default_factory=list)
    modelId: str | None = None
    cimNamespace: str | None = None
    aboutOnlyObjects: int = 0
    identifiedObjects: int = 0
    sshPropertyHits: int = 0
    scenarioTime: str | None = None
    created: str | None = None

    def note(self, raw: RawObject) -> None:
        if raw.cimClass == _MODEL_CLASS:
            self.profileUris.extend(raw.literals("Model.profile"))
            self.modelId = self.modelId or raw.identifier.mrid
            self.scenarioTime = self.scenarioTime or raw.literal("Model.scenarioTime")
            self.created = self.created or raw.literal("Model.created")
            return

        self.classCounts[raw.cimClass] += 1
        if self.cimNamespace is None and isCimNamespace(raw.classNamespace):
            self.cimNamespace = raw.classNamespace
        if raw.isAbout:
            self.aboutOnlyObjects += 1
        else:
            self.identifiedObjects += 1
        self.sshPropertyHits += sum(1 for name in raw.propertyNames if name in _SSH_PROPERTIES)


@dataclass(frozen=True, slots=True)
class DocumentProfile:
    """The identified profile of one CGMES document."""

    path: Path
    profile: Profile
    detectedBy: DetectionSource
    cimNamespace: str | None = None
    modelId: str | None = None
    profileUris: tuple[str, ...] = ()
    objectCount: int = 0
    scenarioTime: str | None = None
    created: str | None = None


def profileFromUri(uri: str) -> Profile | None:
    """Map a CGMES profile URI onto a profile, for both CGMES 2.4 and 3.0."""
    collapsed = re.sub(r"[^a-z0-9]", "", uri.lower())
    for token, profile in _PROFILE_URI_TOKENS:
        if token in collapsed:
            return profile
    return None


def profileFromFilename(path: Path) -> Profile | None:
    """Guess a profile from filename tokens such as ``…_SSH.xml``."""
    tokens = [token for token in re.split(r"[^a-z0-9]+", path.stem.lower()) if token]
    for token, profile in _FILENAME_TOKENS:
        if token in tokens:
            return profile
    return None


def _profileFromContent(evidence: ProfileEvidence) -> Profile | None:
    scores: Counter[Profile] = Counter()
    for cimClass, count in evidence.classCounts.items():
        marker = _MARKER_CLASSES.get(cimClass)
        if marker is not None:
            scores[marker] += count
    if evidence.sshPropertyHits:
        # SSH updates existing objects rather than defining them, so a document
        # made of rdf:about descriptions carrying SSH properties is an SSH file.
        scores[Profile.SSH] += evidence.sshPropertyHits + evidence.aboutOnlyObjects
    if not scores:
        return None
    best, bestScore = scores.most_common(1)[0]
    tied = [profile for profile, score in scores.items() if score == bestScore]
    return best if len(tied) == 1 else None


def detectProfile(path: Path, evidence: ProfileEvidence, diagnostics: Diagnostics) -> DocumentProfile:
    """Identify the CGMES profile of one document."""
    common = {
        "path": path,
        "cimNamespace": evidence.cimNamespace,
        "modelId": evidence.modelId,
        "profileUris": tuple(evidence.profileUris),
        "objectCount": sum(evidence.classCounts.values()),
        "scenarioTime": evidence.scenarioTime,
        "created": evidence.created,
    }

    headerProfiles = [profile for uri in evidence.profileUris if (profile := profileFromUri(uri)) is not None]
    if headerProfiles:
        chosen = Counter(headerProfiles).most_common(1)[0][0]
        return DocumentProfile(profile=chosen, detectedBy=DetectionSource.MODEL_HEADER, **common)

    if evidence.profileUris:
        diagnostics.warn(
            "unrecognisedProfileUri",
            "Model header declares a profile URI that is not recognised",
            document=path.name,
            uris=", ".join(evidence.profileUris),
        )

    fromContent = _profileFromContent(evidence)
    if fromContent is not None:
        diagnostics.info(
            "profileFromContent",
            "Profile derived from document content because no model header declared one",
            document=path.name,
            profile=fromContent.value,
        )
        return DocumentProfile(profile=fromContent, detectedBy=DetectionSource.CONTENT, **common)

    fromFilename = profileFromFilename(path)
    if fromFilename is not None:
        diagnostics.warn(
            "profileFromFilename",
            "Profile guessed from the filename; neither header nor content identified it",
            document=path.name,
            profile=fromFilename.value,
        )
        return DocumentProfile(profile=fromFilename, detectedBy=DetectionSource.FILENAME, **common)

    diagnostics.warn("unknownProfile", "Could not identify the CGMES profile of this document", document=path.name)
    return DocumentProfile(profile=Profile.UNKNOWN, detectedBy=DetectionSource.NONE, **common)
