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

## Ergänzung vom 06.10.2026: Excel-Dreibein

Die neue Multipod-Konvertierung bleibt vollständig im Parser. Drei Excel-Beine
an einem vorhandenen virtuellen SUB-Knoten ergeben genau drei CSV-Einträge:
Die erste Leitungszeile enthält A, B, T-1=C und Y1=X; die zweite A–C ohne B;
die dritte B–C ohne A. Nur die erste Zeile hat T-1/Y1. IDs und übrige Attribute
bleiben an ihren Quellzeilen. Die Verbindungsbedeutung der IDs ändert sich nach
dieser Regel; Excel-Reihenfolge und unterschiedliche Betriebsdaten müssen deshalb
fachlich geprüft werden. T-2/Y2 bleiben leer; vier Beine oder mehrere Stromkreise
am selben X werden nicht automatisch erschlossen.

- **410 Parser-Tests bestanden**, zwei QGIS-Testmodule übersprungen, pandas 3.0.5.
- **59 Tests bestanden** in der echten QGIS-3.40.3-/pandas-2.2.3-Umgebung:
  die bisherigen MJAP-Prüfungen, vier vollständige Assistentenszenarien und
  die neuen Dreibein-Tests.
- Vier Stationspunkte, drei Netzelement-IDs und fünf gültige Linienobjekte:
  A–X, B–X, C–X sowie direkte A–C und B–C.
- Eine Freischaltung der ersten ID enthält alle drei Y-Beine in einem
  MultiLineString; dasselbe gilt für die zugehörige Projektgeometrie.
- Geprüft: vollständige Shape-IDs und Stationspaare, Quell-ID-/Datumserhalt,
  Namen mit Ausschlusszusatz, genau einmal Y1, fehlende T-/Y-Felder der Paarzeilen,
  Zeitfelder, Joins und aktive Stilausdrücke. Ungültige Gruppen, Null-Längen der
  Y-Beine und erzeugte Shape-ID-Kollisionen werden vor dem MJAP-Export abgewiesen.
- Keine GUI-Warnung, keine kritische Meldung und keine Fehler in den geprüften
  aktiven Regelausdrücken. Die bekannte pandas-ABN-Warnung bleibt möglich.

[Wiederholbares Excel-Beispiel mit den erzeugten CSVs und dem tatsächlichen
Assistentenbericht](docs/beispiel/dreibein/README_DE.md). Ein erneuter CLI-Export
mit pandas 3 erzeugt bytegenau dieselben vier CSV-Dateien wie der QGIS-Prüflauf.

Zusätzliche Prüfungen wiederholen:

```bash
bash scripts/test_mjap.sh tests/testMultipod.py -o addopts= -q
```

## Ergänzung vom 06.10.2026: Standardexport und KeyError MJAP-ID

Der einfache CLI-Aufruf mit Excel-Pfad, `-o` und `--details` verwendete bisher
allgemeine Leerzeichen-Platzhalter. MJAP behandelt solche T-/Y-Felder als belegte
Referenzen (`notna()`), findet jedoch keine passenden Stationen. Bei gewöhnlichen
Punkt-zu-Punkt-Zeilen blieb `sk_df` vollständig leer, ohne die Spalte `MJAP-ID`.
Die folgende Attributerzeugung löste dann exakt den gemeldeten KeyError aus.
Dieser Fehler wurde mit dem historischen Format am echten unveränderten Plugin
reproduziert. Andere ungültige Referenzen können denselben Fehler auslösen; die
konkreten Windows-Eingabedaten wurden nicht bereitgestellt.

Der CLI-Standard erzeugt jetzt zwei MJAP-kompatible Netztabellen direkt aus Excel:
UTF-8 mit BOM, Dezimalkomma, echte leere Topologiefelder, passende Mehrfachdatums-
Texte und exakte Typzuordnung. Er validiert strikt und veröffentlicht beide Dateien
mit Rücksetzung bei gewöhnlichen Schreib-/Dateiaustauschfehlern. Das historische
Format ist ausdrücklich über `--legacy` verfügbar. Die Python-API behält den
bisherigen Standard und wählt den sicheren Netzexport mit `mjapNetwork=True`.

Der vollständige Assistent benötigt weiterhin echte, befüllte Freischaltungen und
Projekte. Der Zwei-Tabellen-Export erfindet diese nicht und verändert vorhandene
Begleitdateien im Ausgabeordner nicht. Der Modus `--mjap` bleibt das geprüfte
Viererpaket mit zusätzlichen Quelltabellen.

- **422 Parser-Tests bestanden**, zwei optionale QGIS-Testmodule übersprungen.
- **74 Tests in der echten QGIS-/MJAP-Umgebung bestanden**, darunter vier
  vollständige Assistentenszenarien, die exakte Fehlerreproduktion und der
  korrigierte einfache Aufruf für normale Leitungen und Dreibeine.
- Die Netztabellen des einfachen Aufrufs sind bytegenau identisch mit denen des
  geprüften vollständigen Pakets, sowohl mit pandas 3.0.5 als auch pandas 2.2.3.
- Neue Tests decken strikte Fehlereingaben, Erhalt vorhandener Begleitdateien,
  Zweierpaket-Rücksetzung und die tatsächliche MJAP-Shape-/Attributerzeugung ab.
- Das Plugin wurde nicht verändert. Der reale Windows-Export muss nach der
  Parser-Aktualisierung neu erzeugt und mit den eigenen Daten geprüft werden.

```powershell
python converter.py "C:\Daten\input.xlsx" -o "C:\Daten\output" --details
```

Prüfungen wiederholen:

```bash
bash scripts/test_mjap.sh tests/testMultipod.py tests/testMjapNetwork.py -o addopts= -q
```


## Ergänzung vom 07.10.2026: geprüfter Teil-Export und Pflegeberichte

Der CLI-Standard und `--mjap` schließen Elemente mit Datenfehlern oder Datenwarnungen
aus, einschließlich abhängiger Leitungen, aller Duplikate und ganzer Dreibeine.
Der verbleibende Bestand wird erneut geprüft und vor Veröffentlichung gegen den
MJAP-Vertrag validiert. Mehrteilige ABN werden jetzt ebenfalls vor dem Schreiben
zurückgewiesen. Das MJAP-Plugin selbst wurde nicht verändert.

Automatisch entstehen `Fehlerliste.csv` und `Pflegebericht.html`, auch beim
Abbruch. Excel-Blatt und physische Zeilennummern bleiben zuordenbar; bei
Begleit-CSVs werden Dateipfad und physische CSV-Zeilen berichtet, auch bei
Leerzeilen oder mehrzeiligen Feldern. Die Original-Excel bleibt unverändert.

Nachweise:

- Vollständige Parser-Suite: **453 bestanden, zwei QGIS-Testmodule ohne QGIS übersprungen**.
- Echte QGIS-3.40.3-/pandas-2.2.3-Umgebung: **107 Tests bestanden**. Der neue
  vollständige Assistentenfall exportiert einen gemischten Excel-Bestand,
  schließt drei defekte/abhängige Zeilen aus und erzeugt ohne GUI-Fehlermeldung
  gültige Layer, Joins, Stile und Zeitfelder aus den verbleibenden Daten.
- Gemischtes direktes Netz mit erhaltenem Dreibein: fünf CSV-Netzelemente werden
  im unveränderten MJAP zu sieben Geometrie-/Attributzeilen; kein `KeyError: MJAP-ID`.
- Neuer Pflege-Testbestand prüft Fehler, Warnungen, Stationsabhängigkeiten,
  Duplikate, shape-ID-Kollisionen, beschädigte Dreibeine, alle Elemente gesperrt,
  unveränderte Excel-Eingabe, Berichtsquellen, physische Zeilen und HTML-Maskierung.
- [Dummy-Beispiel](docs/beispiel/teil-export/README_DE.md): 15 Excel-Datenzeilen,
  sieben ausgeschlossen, sechs Stationen und zwei Netzelemente veröffentlicht.

Die sechs Warnungen in den QGIS-Tests stammen aus der bekannten pandas-
Datumsformaterkennung im unveränderten Plugin, einschließlich der gezielten
Legacy-Fehlerreproduktion. Der vollständige Assistentenfall protokolliert keine
GUI-Warnung oder kritische Meldung. Diese Bibliotheksdiagnostik ist kein
elementbezogener Excel-Datenbefund.

Teil-Exportstatus ist **3**; **0** bedeutet keine Ausschlüsse, **2** Abbruch.
Keine nutzbare Leitung oder eine vollständig geleerte erforderliche Begleittabelle
führt weiterhin zum Abbruch, damit kein unbrauchbares MJAP-Paket entsteht.
Der [Pflegeleitfaden](docs/TEIL_EXPORT_UND_PFLEGE_DE.md) erläutert Grenzen und Ablauf.
