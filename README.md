# cgmes2excel

Converts a CGMES export (EQ / SSH / TP / SV / GL) into one Excel workbook with
exactly two worksheets, `Stationen` and `NETZELEMENTE`.

The workbook is an external contract: sheet names, column names, capitalization
and column order are fixed. The path used to *derive* those values is semantic —
CIM relationships are resolved across profiles rather than read out of one file.

```bash
uv run cgmes2excel path/to/export -o netz.xlsx
uv run cgmes2excel export.zip -o netz.xlsx --verbose --trace-file trace.txt
uv run cgmes2excel --print-mapping          # how every column is derived
```

Inputs may be files, directories (searched recursively) or zip archives.

## Architecture

```
inputs      discovery of files / directories / zip members
cgmes/      RDF-XML reader -> identifier normalization -> indexed CimGraph
            profile detection (model header > content > filename)
domain/     semantic traversal: containment, terminals, topology, voltage,
            geography, equipment classification
mapping/    frozen schema + one documented FieldRule per output column
export/     workbook writer + post-write validation of the file on disk
pipeline    sequences the stages and reports the run summary
```

Each layer is separately testable and none reaches around another. Mapping rules
ask `NetworkModel` questions; they never walk the graph themselves, so the
traversal logic exists exactly once.

### Reference resolution

All documents are indexed before any reference is followed, so file order,
element order and cross-profile references are irrelevant. `rdf:ID`,
`rdf:about`, `rdf:resource` and `urn:uuid:` forms normalize to one comparison
key while the original spelling and the `mRID` are preserved. An object
described in several profiles becomes one node whose defining (`rdf:ID`)
declaration wins on conflict.

After loading, every stored reference is swept once so that dangling references
are found even when nothing ever follows them.

### Profile detection

`md:FullModel` / `Model.profile` is authoritative and covers both CGMES 2.4.15
and 3.0 URIs. Without a header, the classes and properties actually present
decide. The filename is only consulted as a last resort, and doing so is logged
as a warning.

## Decisions that carry meaning

**One row per Substation.** A substation spanning several voltage levels stays
one record; `Spannung` lists its distinct nominal voltages highest first, e.g.
`380/220/110`. Multi-voltage substations are logged.

**Which equipment becomes a NETZELEMENTE row.** The default set is
branch-oriented — `ACLineSegment`, `DCLineSegment`, `SeriesCompensator`,
`EquivalentBranch`, `PowerTransformer` — because the columns (Station
Anfang/Ende, Station T-1/T-2, Y-Knoten-1/2) describe elements that span two
stations. Switchgear, busbars and injections are registered but off by default;
`--include-class` / `--only-class` change the set, and objects of known classes
that are not exported are counted in the summary.

**Station columns per equipment category.**

| Category | Station Anfang | Station Ende | Station T-1 / T-2 |
| --- | --- | --- | --- |
| branch, switch | station of terminal 1 | station of terminal 2 | empty |
| transformer | containing substation | empty | stations of winding ends 1 and 2 |
| busbar, injection | station of terminal 1 | empty | empty |

Reading `Station T-1`/`T-2` as the transformer winding stations is an
interpretation. It is isolated in `mapping/elements.py` (`_STATION_STRATEGIES`)
so it can be changed in one place.

**Terminal order** comes from `TransformerEnd.endNumber` first, then
`ACDCTerminal.sequenceNumber`. XML order is never trusted; when neither is
available the order is undetermined and reported as such rather than invented.

**Coordinates.** `xPosition` is longitude and `yPosition` is latitude only in a
geographic CRS. `CoordinateSystem.crsUrn` is checked; a projected system yields
*empty* lat/long plus a warning instead of misleading numbers. A missing
coordinate system is treated as WGS84, as the GL profile prescribes, and that
assumption is logged. Values outside the degree range are rejected.

**Columns with no CGMES source** stay empty behind a stated reason rather than
being guessed: `Eigentümer`, `MJAP-ID`, `IBN`, `ABN`, `relevant für`,
`reales UW`, the OPC names, `ID-OPC`, `ID-UCTE`, `ID-GUID intern-2`, `ID`,
`Geändert`, `Geändert von`. Each empty cell is counted per column in the
summary. `ID-GUID intern-1` carries the real CGMES `mRID`; `Kommentar` carries
`IdentifiedObject.description`; `Elementtyp` carries the CIM class.

**Cell types.** Everything is written as text with an explicit text format so
GUIDs, leading zeros, date-like strings and values starting with `=` cannot be
reinterpreted. The exceptions are `lat`, `long` and the single-valued
NETZELEMENTE `Spannung`, which are numbers. Station `Spannung` stays text
because it may combine several levels.

## Open questions for the domain owner

1. Do `Station T-1`/`T-2` mean the transformer winding stations, as implemented?
2. Should switchgear or busbars appear in NETZELEMENTE by default?
3. Is `Elementtyp` meant to be the CIM class, or a fixed record type from the
   downstream system?
4. Is there a source system for MJAP-ID, the OPC names, IBN/ABN and
   `relevant für` that should be joined in as enrichment data?
5. For a three-winding transformer only two windings fit the sheet; the surplus
   is reported as `terminalsBeyondTargetFormat`. Should such a transformer
   instead produce one row per winding pair?

## Diagnostics

`--trace-file` writes the derivation of every cell of every row:

```
NETZELEMENTE row 4 (source mRID LX)
    Station Anfang: Terminal TLXA -> TopologicalNode Knoten SUBD 380 -> VoltageLevel ... -> Substation Umspannwerk Delta
    Station Ende:   Terminal TLXB -> TopologicalNode Grenzknoten X -> unavailable (nodeNotInAVoltageLevel)
```

Console logging is coloured when the terminal supports it and falls back to
plain text otherwise; `--log-file` output is never coloured. Repeated findings
of one kind are rate-limited on the console but counted in full.

## Development

```bash
uv run pytest          # 316 tests
```

Style: camelCase for functions, methods, variables and fields; PascalCase for
classes; UPPER_SNAKE_CASE for module constants.
