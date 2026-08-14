# Excel → Stationen.csv / Netzelemente.csv

Konvertiert eine Excel-Netzinventarliste in **genau zwei** CSV-Dateien:
`Stationen.csv` und `Netzelemente.csv`.

Die Output-Header sind ein externer Vertrag: Schreibweise, Reihenfolge, Bindestriche,
Leerzeichen, Groß-/Kleinschreibung und Umlaute werden nicht verändert.

---

## Installation

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Python 3.11+. Pflichtabhängigkeiten: `pandas`, `openpyxl`, `colorlog`.
`python-calamine` ist **optional** und beschleunigt nur das Einlesen (siehe [Performance](#performance)).

## Verwendung

```bash
python converter.py input.xlsx
```

```bash
python converter.py input.xlsx --output-dir ./output
```

| Option | Bedeutung |
| --- | --- |
| `-o`, `--output-dir` | Zielverzeichnis (Default: aktuelles Verzeichnis) |
| `--sheet` | Worksheet als Name oder 0-basierter Index (Default: erstes Worksheet) |
| `--header-row` | 1-basierte Excel-Zeile der Kopfzeile (Default: automatische Erkennung) |
| `--engine` | `auto` (Default), `openpyxl` oder `calamine` |
| `--encoding` | CSV-Kodierung (Default `utf-8`; `utf-8-sig` für Excel-freundliche BOM) |
| `--quote-all` | Jedes Feld quoten statt nur die notwendigen |
| `--log-level` | `DEBUG`, `INFO` (Default), `WARNING`, `ERROR`, `CRITICAL` |
| `--color` / `--no-color` | Farbige Logausgabe erzwingen bzw. abschalten |

**Exit-Codes:** `0` Erfolg · `2` fataler Validierungsfehler · `1` unerwarteter Fehler.

Ohne `--sheet` wird das erste Worksheet verwendet und sein Name per `INFO` geloggt.

## Ablauf

```
Excel roh lesen               (ohne Annahme über die Kopfzeile)
  → Kopfzeile suchen          (Vorspann darüber verwerfen)
  → Spalten normalisieren       (trimmen, kanonische Schreibweise)
  → Inputschema validieren      (Pflichtspalten vorhanden?)
  → ELEMENT-TYPE klassifizieren (unbekannter Typ = fatal, Abbruch)
  → Stationen (SUB) erfassen
  → Stationsindex über ELEMENT ID aufbauen
  → Netzelemente erfassen
  → ALLE Validierungen          (Referenzen, Dubletten, Output-Schema)
  → erst jetzt: Stationen.csv + Netzelemente.csv schreiben
```

Es wird **nichts** geschrieben, solange nicht alle Validierungen fehlerfrei sind.
Beide Dateien entstehen zunächst als temporäre Dateien und werden erst danach atomar
an ihren Zielnamen verschoben – auch ein I/O-Fehler hinterlässt also keinen halben Output.

## Kopfzeile finden

Die Kopfzeile steht nicht zwingend in Zeile 1 – in der Praxis liegen Titel, Stand und
Hinweise darüber. Ihre Position wird deshalb **automatisch ermittelt**, eine feste
Zeilennummer ist nirgends im Code verdrahtet.

Die Datei wird ohne Kopfzeilenannahme eingelesen. Anschließend wird jede der ersten
100 Zeilen bewertet: gezählt wird, wie viele der 13 Pflichtspalten sie als Überschrift
enthält (case-insensitiv, whitespace-tolerant). Die erste Zeile mit der höchsten
Trefferzahl gewinnt; bei vollständiger Übereinstimmung bricht die Suche sofort ab.
**Alles oberhalb dieser Zeile wird verworfen** – der Vorspann muss weder ein bestimmtes
Format haben noch leer sein.

```
INFO     Header detected in row 5 - skipping 4 leading row(s) above it.
INFO     Found 6 data row(s) below the header.
```

Alle Zeilennummern in Warnungen und Fehlermeldungen beziehen sich weiterhin auf die
**echte Excel-Zeile**, nicht auf die Position innerhalb der Daten – bei Kopfzeile in
Zeile 5 beginnt die erste Datenzeile also bei `Row: 6`.

Sonderfälle:

* Passt eine Zeile nur schwach (weniger als die Hälfte der Pflichtspalten), wird sie
  trotzdem verwendet, aber mit einer `WARNING` versehen. Die anschließende Schemaprüfung
  nennt dann exakt die fehlende Spalte – hilfreicher als ein pauschales „nicht gefunden".
* Enthält keine der abgesuchten Zeilen auch nur eine Pflichtspalte, bricht die Conversion
  mit einem klaren Hinweis auf `--header-row` ab.
* Ein Vorspanntext, in dem einzelne Spaltennamen vorkommen, verdrängt die echte
  Kopfzeile nicht – diese trifft immer mehr Spalten.
* Leere Zellen in der Kopfzeile erhalten den Platzhalternamen `Unnamed: <Position>`.
* Mit `--header-row 5` lässt sich die Erkennung jederzeit übersteuern.

Die Erkennung kostet nichts Messbares (0,3 ms bei 200.000 Zeilen), da nur die ersten
Zeilen betrachtet werden und ein vollständiger Treffer die Suche beendet.

## Module

| Datei | Verantwortung |
| --- | --- |
| `converter.py` | CLI-Einstiegspunkt |
| `excelToCsv/cli.py` | Argumente, Exit-Codes |
| `excelToCsv/schema.py` | Unveränderlicher Vertrag: Input-Pflichtspalten, ELEMENT-TYPEs, Output-Header |
| `excelToCsv/reader.py` | Excel-I/O, Kopfzeilenerkennung, Spaltennormalisierung, Schemaprüfung |
| `excelToCsv/normalize.py` | Reine Wertfunktionen (Datum, Spannung, Koordinate, Boolean, Text) |
| `excelToCsv/relevance.py` | Dynamische `Interesting/Relevant for`-Spalten → JSON-Liste |
| `excelToCsv/stations.py` | `SUB` → Stationen-Datensatz |
| `excelToCsv/networkElements.py` | alle übrigen Typen → Netzelemente-Datensatz |
| `excelToCsv/validate.py` | Typprüfung, Dubletten, Referenzintegrität, Output-Schema |
| `excelToCsv/writer.py` | Atomares CSV-Schreiben |
| `excelToCsv/pipeline.py` | Orchestrierung (`convertTable` ist I/O-frei und direkt testbar) |
| `excelToCsv/issues.py` | Einsammeln/Formatieren von Fehlern und Warnungen |
| `excelToCsv/loggingSetup.py` | Farbiges Logging (`colorlog`, ANSI-Fallback) |

Transformation und I/O sind getrennt: `pipeline.convertTable(table, logger)` arbeitet rein
auf Daten und lässt sich ohne Excel-Datei testen.

## Fehlerstrategie

* `INFO` – normaler Programmablauf.
* `WARNING` – fachlich tolerierbar, Conversion läuft weiter.
* `ERROR` – **immer fatal**, Conversion bricht ab, es entstehen keine CSV-Dateien.

Jede Meldung enthält so viel Kontext wie möglich:

```
ERROR    Validation failed.
Row: 184
ELEMENT ID: LINE_471
ELEMENT-TYPE: LINE
Field: Station 2
Value: <empty>
Problem: Required station reference is missing.
Expected: LINE requires Station 1 and Station 2.
```

**Bewusste Abweichung von der Vorgabe:** Innerhalb einer Phase werden *alle* Fehler
eingesammelt und geloggt, und erst an der Phasengrenze wird abgebrochen. Der Anwender
sieht damit in einem Lauf jedes Problem statt nur des ersten. Die harte Zusage bleibt
unverändert: bei mindestens einem `ERROR` entsteht keine einzige CSV-Datei.

## Fachliche Regeln

**Klassifikation.** `SUB` → `Stationen.csv`. `CAP BUB DCL GEN IND LINE LOAD PPL PROD TIE TRA`
→ `Netzelemente.csv`. Prüfung case-insensitiv, intern immer Uppercase.
Unbekannter `ELEMENT-TYPE` = fatal.

**Virtuelle Stationen.** Stationsname = Teil vor dem *letzten* `_`. Beginnt er mit `X`,
gilt die Station als virtueller X-Knoten (`reales UW = Falsch`), sonst `Wahr`.
Virtuelle Stationen stehen bereits als eigene `SUB`-Zeilen im Input – es werden keine
erzeugt und keine Koordinaten berechnet.

**Koordinaten.** Für jede `SUB`-Station (real wie virtuell) sind `Latitude` und `Longitude`
Pflicht. `52,459373` wird zu `52.459373`. Bereichsprüfung: Lat −90…90, Long −180…180.
Fehlend oder ungültig = fatal.

**Datum.** `STARTLIFETIME → IBN`, `ENDLIFETIME → ABN`, Zielformat immer `TT.MM.JJJJ`.
Echte Excel-Datumswerte, Seriennummern und parsebare Strings werden unterstützt
(ISO zuerst, danach tagesorientierte Formate – es wird nie geraten).
Leer bleibt leer, nicht interpretierbar = fatal.

**Spannung.** `380.0 → 380`, `380.0/110.0 → 380/110`, `DC → DC` (Text, nie numerisch).
In `Stationen.csv` als JSON-Liste (`["380","110"]`), in `Netzelemente.csv` als Text (`380/110`).

**relevant für.** Spalten mit `Interesting` bzw. `Relevant for` im Header werden dynamisch
erkannt, der Name aus dem Header extrahiert (bevorzugt aus der Klammer). `TRUE`: `1`, `True`,
`true`, `TRUE`. `FALSE`: `0`, `False`, `false`, `FALSE`, leer, `NaN`. Alles andere → `WARNING`,
und der Eintrag gilt **nicht** als `TRUE`. Ergebnis ist eine echte JSON-Liste: `["50Hertz","TennetD"]`.
`OPC INTERESTING ASSET` ist ausdrücklich keine Relevanz-Spalte.

**Stationsreferenzen.** `LINE TRA TIE DCL` benötigen `Station 1` **und** `Station 2` – fehlt eine,
ist das fatal. Bei `CAP BUB GEN IND LOAD PPL PROD` wird stattdessen das Literal `NaN`
geschrieben und eine `WARNING` geloggt. Jede *gesetzte* Referenz muss auf eine existierende
`SUB`-Zeile zeigen, sonst fatal – unabhängig von der Zeilenreihenfolge im Excel.

**Dubletten.** Doppelte Stations-`ELEMENT ID` = fatal, unter Nennung aller betroffenen Zeilen.
Doppelte Netzelement-IDs sind nur dann fatal, wenn sich die Datensätze unterscheiden;
vollständig identische Zeilen ergeben eine `WARNING`.

**Ignoriert.** `CCR/ROA`, `ACTION`, `Map Multipod`, `Multipod`, `OPC INTERESTING ASSET`,
`OPC Map only`, `interconnector …`. Keine Multipod-, keine OPC-Logik.

**Felder ohne Quelle** (`Region`, `ID-GUID intern-1/2`, `ID-OPC`, `…OPC-Name`, `IBN/ABN - Mehrfach`,
`Station T-1/T-2`, `Y-Knoten-1/2`, `ID` bei Netzelementen) bleiben leer. Es werden keine GUIDs,
Koordinaten oder fachlichen Werte erfunden.

### Zusätzliche Regeln, die die Vorgabe offen ließ

| Situation | Verhalten |
| --- | --- |
| Kopfzeile nicht in Zeile 1 | automatisch gesucht, Vorspann verworfen (siehe [Kopfzeile finden](#kopfzeile-finden)) |
| `ELEMENT ID` leer | fatal – ohne MJAP-ID ist der Datensatz nicht verwendbar |
| Komplett leere Excel-Zeile | wird übersprungen und per `INFO` gemeldet |
| Station ohne `_` in der ID | `WARNING`, die volle ID gilt als Stationsname |
| Leere `VOLTAGE-LEVEL` bei `SUB` | `[]` (leere JSON-Liste) |
| Koordinate mit Punkt *und* Komma | letzter Separator gilt als Dezimaltrenner, `WARNING` |
| Doppelte Spaltennamen nach Normalisierung | fatal (Zuordnung wäre mehrdeutig) |

## Output

UTF-8, Komma als Separator, keine Indexspalte, keine Zusatzspalten, LF als Zeilenende.
Felder werden RFC-4180-konform gequotet – eine JSON-Liste erscheint in der Datei
als `"[""380"",""110""]"` und wird von jedem CSV-Reader wieder als `["380","110"]` gelesen.
Mit `--quote-all` wird stattdessen jedes Feld gequotet.

## Tests

```bash
.venv/bin/python -m pytest
```

141 Tests, u. a. alle 25 geforderten Fälle:

| Datei | Abgedeckt |
| --- | --- |
| `tests/testHeaderDetection.py` | Kopfzeile in Zeile 5, echte Zeilennummern, `--header-row`, fehlende Kopfzeile |
| `tests/testNormalize.py` | Spannung (6, 7), Koordinaten (5), Datum (9, 10), Boolean (19–21) |
| `tests/testStations.py` | reale/virtuelle Station (1, 2), fehlende Koordinaten (3, 4), Spannungs-JSON (8), Dubletten (22) |
| `tests/testNetworkElements.py` | LINE/TRA/TIE/DCL (11–15), GEN → `NaN` (16), unbekannte Referenz (17), unbekannter Typ (18) |
| `tests/testRelevance.py` | `relevant für` (19–21) |
| `tests/testOutput.py` | Header-Reihenfolge (23, 24), keine CSVs bei fatalem Fehler (25), CLI, Engines |

## Performance

Messung auf 200.000 Zeilen (100k Stationen + 100k Netzelemente):

| Phase | openpyxl | calamine |
| --- | --- | --- |
| Lesen | 18,9 s | 3,4 s |
| Transformation + Validierung | 7,4 s | 7,4 s |
| Schreiben | 0,8 s | 0,8 s |
| **Gesamt** | **27,9 s** | **11,9 s** |

Das Einlesen dominiert, deshalb ist `python-calamine` als optionaler Beschleuniger
eingebunden: `--engine auto` (Default) nutzt es, wenn es installiert ist, und fällt sonst
auf `openpyxl` zurück. Beide Engines liefern nachweislich byte-identische CSVs
(`testBothReadEnginesProduceIdenticalOutput`).

Im Transformationspfad wird spaltenweise über NumPy-Objekt-Arrays gearbeitet statt
zeilenweise über `DataFrame.iterrows()`. Die `relevant für`-Spalte wird über eine Bitmaske
je Zeile berechnet, sodass jede vorkommende Kombination nur einmal als JSON serialisiert wird.
