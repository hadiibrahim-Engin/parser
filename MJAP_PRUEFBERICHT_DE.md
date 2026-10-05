# Parser → MJAP: Prüfbericht vom 05.10.2026

Geprüft wurden der Parser und das benachbarte MJAP-Plugin einschließlich seines
vollständigen Visualisierungsassistenten. Der MJAP-Quellcode blieb bei dieser
Prüfung unverändert (Git-Basis `2594712`). Die Anpassungen liegen im Parser.

## Erwartete Tabellen

| Tabelle | Pflichtinhalt im geprüften Modus |
| --- | --- |
| `Stationen.csv` | Die vorhandenen 20 Vertrags-Spalten; eindeutige MJAP-ID, numerische lat/long, gültige IBN |
| `Netzelemente.csv` | Die vorhandenen 30 Vertrags-Spalten; eindeutige MJAP-ID, beide Stationsreferenzen, gültige IBN; `TRA` → `Trafo` |
| `Freischaltungen.csv` | `MJAP-ID`, `Netzelement:MJAP-ID`, `interne ID`, `von`, `bis`, `Projekt`; zusätzlich `Maßnahme`, `Schaltungsart`, `Schaltung` für die vorhandenen Stile |
| `Projekte.csv` | `Projektname`, `betroffener Standort`, `Umsetzungzeitraum von`, `Umsetzungzeitraum bis` |

Der Parser ergänzt die drei optionalen Schaltungsfelder bei Bedarf leer. Datums-
und Referenzfehler werden vor dem Schreiben abgewiesen. Spaltennamen werden
nicht übersetzt. Die vollständigen 20-/30-Spaltenlisten stehen in `README.md` und
`excelToCsv/schema.py`. Alle vier Ausgaben verwenden Komma als CSV-Trennzeichen,
UTF-8 mit BOM und `TT.MM.JJJJ` für Termine; Koordinaten verwenden Dezimalkomma.

## Gefundene Probleme und Maßnahmen

1. **Leere Begleittabellen:** Die CSV-Konvertierung selbst gelingt, aber der
   XLSX-Layerimport erkennt Kopfzeilen ohne Daten als `Field1`, … und einen
   vermeintlichen Datensatz. Der vollständige Assistent bricht dann mit
   `KeyError: Standort_von` ab. Leere oder fehlende Begleittabellen werden im
   MJAP-Modus jetzt abgewiesen; es werden keine Ersatzdatensätze erzeugt.
2. **Fehlende Betriebsdaten:** Bei vollständig leeren Datumsfeldern entstanden
   falsche Excel-Feldnamen; damit fehlten die Join-Felder und Stil-/Zeitfelder.
   Der geprüfte Modus verlangt deshalb gültige IBN-Daten. Unbekanntes ABN bleibt
   möglich und wird nicht durch einen erfundenen Endtermin ersetzt.
3. **Datentypen:** Die CSV-Felder für unbekanntes ABN bleiben Text. Dadurch entfällt
   die pandas-`FutureWarning` bei MJAPs Übernahme des Mehrfachterminwerts. Die
   harmlose Warnung zur Formatvermutung bei vollständig leerem ABN bleibt im
   unveränderten Plugin bestehen und wird in Tests ausdrücklich erfasst.
4. **Geometrie-/Joinrisiken:** Null-Längen durch gleiche Endkoordinaten,
   nicht exportierbare oder zu lange IDs, fehlende Stationsreferenzen,
   doppelte Kopfzeilen und reservierte Schaltungsspalten werden abgefangen.
5. **Unvollständige Pakete:** Alle vier CSVs werden vor Veröffentlichung
   serialisiert. Tests simulieren einen Fehler beim vierten Schreibvorgang und
   beim vierten Dateiaustausch; in beiden Fällen bleibt das alte Paket erhalten.

## Nachgewiesene Ergebnisse

- **400 Parser-Tests bestanden**, zwei optionale QGIS-Testmodule ohne QGIS
  übersprungen (Parser-Umgebung: pandas 3.0.5).
- **35 MJAP-/QGIS-Tests bestanden** in QGIS 3.40.3, Python 3.12, pandas 2.2.3.
- Drei vollständige Assistentenläufe: unbekanntes ABN, bekannte Betriebsenden,
  sowie kombinierte Leitungs- und Transformator-Schaltungen.
- Geprüft: gültige Geometrien mit passenden GeoPackage-Typen, erwartete
  Datensatzanzahlen, keine verlorenen Schaltungen, Attribut- und Projektjoins,
  Zeitfelder mit korrekten Namen, aktive Stilausdrücke ohne Feldfehler,
  leere Fehlerberichte und speicherbare QGIS-Projekte.
- Keine GUI-Warnung oder kritische GUI-Meldung in diesen drei Assistentenläufen.
  Bei unbekanntem ABN wird ausschließlich die bekannte pandas-Datumswarnung
  zugelassen; beim Szenario mit bekannten Betriebsenden treten keine Python-
  Warnungen auf.
- Die Länderlayer für DE/NL/BE/FR bleiben durch die bestehenden Kartentests
  abgedeckt. Zusätzliche Ländergrenzen benötigen keine Änderung am Plugin.

Die Beispieldatensätze dieser Tests sind ausschließlich Dummy-Daten in temporären
Verzeichnissen. Das ersetzt keinen fachlichen Test mit tatsächlichen Netzdaten.
Andere QGIS-/pandas-Versionen, geänderte MJAP-Feldzuordnungen sowie paralleles
Lesen während des Exports sind nicht zugesichert.

## Reproduzieren

Im Parser-Verzeichnis:

```bash
.venv/bin/python -m pytest
bash scripts/test_mjap.sh
.venv/bin/python converter.py input.xlsx --mjap \
  --freischaltungen Freischaltungen.csv --projekte Projekte.csv \
  -o output/mjap
```

Die QGIS-Testumgebung kommt aus `../mjap_plugin/.local-env`; alternativ
`QGIS_ENV` auf den absoluten Pfad einer kompatiblen PyQGIS-Umgebung setzen.
Der Teststarter verwendet echte QGIS-/GDAL-/SpatiaLite-Bibliotheken. Nur die
Desktop-Schnittstelle, Ordnerauswahl und Meldungsanzeige sind im Test angepasst.
