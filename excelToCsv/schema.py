"""Unveränderlicher Vertrag: Input-Anforderungen und exakte Output-Header.

Die Output-Spalten sind ein externer Vertrag. Schreibweise, Reihenfolge,
Bindestriche, Leerzeichen, Groß-/Kleinschreibung und Umlaute dürfen NICHT
verändert werden.
"""

from __future__ import annotations

from typing import Final

# --------------------------------------------------------------------------- #
# Input
# --------------------------------------------------------------------------- #

COL_TSO: Final = "TSO"
COL_ELEMENT_ID: Final = "ELEMENT ID"
COL_LONG_NAME: Final = "LONG-NAME"
COL_DESCRIPTION: Final = "DESCRIPTION"
COL_LATITUDE: Final = "Latitude"
COL_LONGITUDE: Final = "Longitude"
COL_STATION_1: Final = "Station 1"
COL_STATION_2: Final = "Station 2"
COL_VOLTAGE_LEVEL: Final = "VOLTAGE-LEVEL"
COL_ELEMENT_TYPE: Final = "ELEMENT-TYPE"
COL_UCTE_CODE: Final = "UCTE CODE"
COL_STARTLIFETIME: Final = "STARTLIFETIME"
COL_ENDLIFETIME: Final = "ENDLIFETIME"

#: Spalten, ohne die keine Conversion möglich ist.
REQUIRED_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    COL_TSO,
    COL_ELEMENT_ID,
    COL_LONG_NAME,
    COL_DESCRIPTION,
    COL_LATITUDE,
    COL_LONGITUDE,
    COL_STATION_1,
    COL_STATION_2,
    COL_VOLTAGE_LEVEL,
    COL_ELEMENT_TYPE,
    COL_UCTE_CODE,
    COL_STARTLIFETIME,
    COL_ENDLIFETIME,
)

#: Bekannte, aber fachlich nicht ausgewertete Spalten. Dürfen fehlen.
IGNORED_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "Map Multipod",
    "ACTION",
    "OPC INTERESTING ASSET",
    "Multipod",
    "CCR/ROA",
    "OPC Map only",
)

#: Alle Spalten, deren kanonische Schreibweise wir kennen (für das Rename).
KNOWN_INPUT_COLUMNS: Final[tuple[str, ...]] = REQUIRED_INPUT_COLUMNS + IGNORED_INPUT_COLUMNS

# --------------------------------------------------------------------------- #
# ELEMENT-TYPE
# --------------------------------------------------------------------------- #

STATION_TYPE: Final = "SUB"

#: Netzelement-Typen, bei denen BEIDE Stationsreferenzen zwingend sind.
BOTH_STATIONS_REQUIRED: Final[frozenset[str]] = frozenset({"LINE", "TRA", "TIE", "DCL"})

#: Netzelement-Typen, bei denen fehlende Stationsreferenzen tolerierbar sind.
STATIONS_OPTIONAL: Final[frozenset[str]] = frozenset(
    {"CAP", "BUB", "GEN", "IND", "LOAD", "PPL", "PROD"}
)

#: Alle gültigen ELEMENT-TYPE-Werte (immer Uppercase).
VALID_ELEMENT_TYPES: Final[frozenset[str]] = (
    frozenset({STATION_TYPE}) | BOTH_STATIONS_REQUIRED | STATIONS_OPTIONAL
)

#: Literalwert für eine fehlende, aber tolerierte Stationsreferenz.
MISSING_STATION_LITERAL: Final = "NaN"

#: Exakte Strings für "reales UW".
REAL_STATION_TRUE: Final = "Wahr"
REAL_STATION_FALSE: Final = "Falsch"

# --------------------------------------------------------------------------- #
# Output: Stationen.csv
# --------------------------------------------------------------------------- #

STATIONS_FILENAME: Final = "Stationen.csv"

STATION_COLUMNS: Final[tuple[str, ...]] = (
    "Eigentümer",
    "MJAP-ID",
    "Stationsname - Langname",
    "lat",
    "long",
    "Spannung",
    "IBN",
    "ABN",
    "Stationsname - Kurzname",
    "reales UW",
    "Stationsname - OPC-Name",
    "ID-GUID intern-1",
    "ID-GUID intern-2",
    "ID-OPC",
    "ID-UCTE",
    "relevant für",
    "ID",
    "Kommentar",
    "IBN - Mehrfach",
    "ABN - Mehrfach",
)

# --------------------------------------------------------------------------- #
# Output: Netzelemente.csv
# --------------------------------------------------------------------------- #

NETWORK_ELEMENTS_FILENAME: Final = "Netzelemente.csv"

NETWORK_ELEMENT_COLUMNS: Final[tuple[str, ...]] = (
    "Eigentümer",
    "MJAP-ID",
    "Stromkreisname - Langname",
    "Region",
    "Element Typ",
    "Spannung",
    "relevant für",
    "IBN",
    "ABN",
    "IBN - Mehrfach",
    "ABN - Mehrfach",
    "Station Anfang",
    "Station Ende",
    "Station T-1",
    "Station T-2",
    "Y-Knoten-1",
    "Y-Knoten-2",
    "Stromkreisname - Kurzname",
    "Stromkreisname - OPC-Name",
    "ID-GUID intern-1",
    "ID-GUID intern-2",
    "ID-OPC",
    "ID-UCTE",
    "ID",
    "Station Anfang:MJAP-ID",
    "Station Ende:MJAP-ID",
    "Station T-1:MJAP-ID",
    "Station T-2:MJAP-ID",
    "Y-Knoten-1: MJAP-ID",
    "Y-Knoten-2: MJAP-ID",
)
