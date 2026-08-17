"""Configurable naming of the target format.

The output headers and the ``Element Typ`` values are a contract with the
consuming system - and that contract changes without the converter changing.
A JSON file therefore renames output columns and translates element types, so a
rename never requires a code change:

.. code-block:: json

    {
      "elementTypes": {"LINE": "Stromkreis", "SUB": "Station"},
      "stationColumns": {"MJAP-ID": "Anlagen-ID"},
      "networkElementColumns": {"Element Typ": "Betriebsmitteltyp"}
    }

This affects the **target format only**. Input column names are untouched -
they are resolved by :mod:`excelToCsv.reader` against the canonical spellings.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from excelToCsv.errors import ConversionError
from excelToCsv.schema import (
    NETWORK_ELEMENT_COLUMNS,
    NETWORK_ELEMENTS_FILENAME,
    STATION_COLUMNS,
    STATIONS_FILENAME,
)

#: Key of the element type translations inside the JSON file.
ELEMENT_TYPES_KEY = "elementTypes"

#: Keys of the two column rename maps.
STATION_COLUMNS_KEY = "stationColumns"
NETWORK_ELEMENT_COLUMNS_KEY = "networkElementColumns"

KNOWN_KEYS = frozenset({ELEMENT_TYPES_KEY, STATION_COLUMNS_KEY, NETWORK_ELEMENT_COLUMNS_KEY})

#: Column holding the element type in ``Netzelemente.csv``.
ELEMENT_TYPE_COLUMN = "Element Typ"


@dataclass(frozen=True, slots=True)
class TargetFormat:
    """Renames and translations applied to the finished records before writing."""

    elementTypes: dict[str, str] = field(default_factory=dict)
    stationColumns: dict[str, str] = field(default_factory=dict)
    networkElementColumns: dict[str, str] = field(default_factory=dict)

    @property
    def isEmpty(self) -> bool:
        """``True`` when nothing would be renamed or translated."""
        return not (self.elementTypes or self.stationColumns or self.networkElementColumns)

    def translateElementType(self, value: str) -> str:
        """Translate one ``ELEMENT-TYPE`` value; unmapped values stay unchanged."""
        return self.elementTypes.get(value, value)

    def applyToStations(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Apply the station column renames."""
        return _renameColumns(frame, self.stationColumns)

    def applyToNetworkElements(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Translate the element types, then apply the column renames."""
        if self.elementTypes and ELEMENT_TYPE_COLUMN in frame.columns:
            frame = frame.copy()
            frame[ELEMENT_TYPE_COLUMN] = [
                self.translateElementType(value)
                for value in frame[ELEMENT_TYPE_COLUMN].to_numpy(dtype=object)
            ]
        return _renameColumns(frame, self.networkElementColumns)


def _renameColumns(frame: pd.DataFrame, renames: dict[str, str]) -> pd.DataFrame:
    """Rename columns in place of a copy, keeping the original order."""
    if not renames:
        return frame
    renamed = frame.copy()
    renamed.columns = pd.Index([renames.get(column, column) for column in frame.columns])
    return renamed


def _readMapping(
    raw: dict[str, object],
    key: str,
    path: Path,
) -> dict[str, str]:
    """Read one string->string mapping out of the parsed JSON file."""
    value = raw.get(key, {})
    if not isinstance(value, dict):
        raise ConversionError(f"'{key}' in {path} must be an object of name/value pairs")
    mapping: dict[str, str] = {}
    for source, target in value.items():
        if not isinstance(target, str):
            raise ConversionError(f"'{key}.{source}' in {path} must map to a string")
        mapping[str(source)] = target
    return mapping


def _warnUnknownColumns(
    renames: dict[str, str],
    columns: tuple[str, ...],
    filename: str,
    logger: logging.Logger,
) -> None:
    """Point out renames whose source column does not exist in the contract."""
    unknown = sorted(set(renames) - set(columns))
    if unknown:
        logger.warning(
            "%s: %d rename(s) target a column that does not exist in %s and will have "
            "no effect: %s",
            "Target format",
            len(unknown),
            filename,
            ", ".join(unknown),
        )


def _rejectDuplicateTargets(
    renames: dict[str, str],
    columns: tuple[str, ...],
    filename: str,
) -> None:
    """Refuse a rename that would give two columns the same name."""
    resulting = [renames.get(column, column) for column in columns]
    duplicates = sorted({name for name in resulting if resulting.count(name) > 1})
    if duplicates:
        raise ConversionError(
            f"Target format renames produce duplicate column(s) in {filename}: "
            f"{', '.join(duplicates)}"
        )


def loadTargetFormat(path: Path | None, logger: logging.Logger) -> TargetFormat:
    """Load the target format definition; ``None`` yields the untouched contract.

    Raises:
        ConversionError: If the file is missing, not valid JSON, or would produce
            duplicate column names.
    """
    if path is None:
        return TargetFormat()

    if not path.is_file():
        logger.error("Target format file not found: %s", path)
        raise ConversionError(f"Target format file not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Cannot read the target format file %s: %s", path, exc)
        raise ConversionError(f"Cannot read the target format file: {path}") from exc

    if not isinstance(raw, dict):
        raise ConversionError(f"{path} must contain a JSON object at the top level")

    # Keys starting with "_" are the usual stand-in for comments in JSON.
    unexpected = sorted(key for key in set(raw) - KNOWN_KEYS if not key.startswith("_"))
    if unexpected:
        logger.warning(
            "Ignoring unknown key(s) in %s: %s. Known keys: %s",
            path,
            ", ".join(unexpected),
            ", ".join(sorted(KNOWN_KEYS)),
        )

    targetFormat = TargetFormat(
        elementTypes=_readMapping(raw, ELEMENT_TYPES_KEY, path),
        stationColumns=_readMapping(raw, STATION_COLUMNS_KEY, path),
        networkElementColumns=_readMapping(raw, NETWORK_ELEMENT_COLUMNS_KEY, path),
    )

    _warnUnknownColumns(targetFormat.stationColumns, STATION_COLUMNS, STATIONS_FILENAME, logger)
    _warnUnknownColumns(
        targetFormat.networkElementColumns,
        NETWORK_ELEMENT_COLUMNS,
        NETWORK_ELEMENTS_FILENAME,
        logger,
    )
    _rejectDuplicateTargets(targetFormat.stationColumns, STATION_COLUMNS, STATIONS_FILENAME)
    _rejectDuplicateTargets(
        targetFormat.networkElementColumns, NETWORK_ELEMENT_COLUMNS, NETWORK_ELEMENTS_FILENAME
    )

    logger.info(
        "Target format loaded from %s: %d element type(s), %d station column(s), "
        "%d network element column(s) renamed.",
        path,
        len(targetFormat.elementTypes),
        len(targetFormat.stationColumns),
        len(targetFormat.networkElementColumns),
    )
    return targetFormat
