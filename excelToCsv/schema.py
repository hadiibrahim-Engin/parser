"""The immutable contract: input requirements and the exact output headers.

The output columns are an external contract. Spelling, order, hyphens, spaces,
capitalization and umlauts must NOT be changed.
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

#: Columns without which no conversion is possible.
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

#: Reference to the virtual station shared by the legs of a multipod line.
COL_MULTIPOD: Final = "Multipod"

#: Columns that carry business logic but may legitimately be absent.
OPTIONAL_INPUT_COLUMNS: Final[tuple[str, ...]] = (COL_MULTIPOD,)

#: Known columns that carry no business logic here. They may be absent.
#: ``Map Multipod`` stays irrelevant - only ``Multipod`` itself is evaluated.
IGNORED_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    "Map Multipod",
    "ACTION",
    "OPC INTERESTING ASSET",
    "CCR/ROA",
    "OPC Map only",
)

#: Every column whose canonical spelling is known (used for the rename).
KNOWN_INPUT_COLUMNS: Final[tuple[str, ...]] = (
    REQUIRED_INPUT_COLUMNS + OPTIONAL_INPUT_COLUMNS + IGNORED_INPUT_COLUMNS
)

# --------------------------------------------------------------------------- #
# ELEMENT-TYPE
# --------------------------------------------------------------------------- #

STATION_TYPE: Final = "SUB"

#: Network element types where BOTH station references are mandatory.
BOTH_STATIONS_REQUIRED: Final[frozenset[str]] = frozenset({"LINE", "TRA", "TIE", "DCL"})

#: Network element types where a missing station reference is tolerable.
STATIONS_OPTIONAL: Final[frozenset[str]] = frozenset(
    {"CAP", "BUB", "GEN", "IND", "LOAD", "PPL", "PROD"}
)

#: All valid ELEMENT-TYPE values (always uppercase).
VALID_ELEMENT_TYPES: Final[frozenset[str]] = (
    frozenset({STATION_TYPE}) | BOTH_STATIONS_REQUIRED | STATIONS_OPTIONAL
)

#: Literal written for a missing but tolerated station reference.
MISSING_STATION_LITERAL: Final = "NaN"

#: Filler for columns that are empty in EVERY row.
#:
#: ``pandas.read_csv`` infers the dtype of such a column as ``float64`` full of
#: ``NaN``, which makes the ``.str`` accessor unusable downstream. A single space
#: carries no business meaning, is indistinguishable from empty in a spreadsheet,
#: and is enough for pandas to infer a text column. It is deliberately NOT a
#: business value - inventing one would put fabricated data into the target system.
DEFAULT_EMPTY_PLACEHOLDER: Final = " "

#: The exact strings for "reales UW".
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
