# Excel-Dreibein → drei CSV-Einträge → MJAP

**Ausschließlich Dummy-Daten. Excel ist die Eingabe; die CSVs wurden automatisch
vom Parser erzeugt und unverändert im echten MJAP-Assistenten geprüft.**

`DUMMY_Dreibein.xlsx` enthält vier SUB-Zeilen und drei LINE-Zeilen.
Der virtuelle Knoten `XStationK_380` besitzt eigene Koordinaten und den
Eigentümer `50Hertz`. Die drei äußeren Stationen gehören zu `Amprion`.

| Excel-Leitungszeile | LONG-NAME | Station 1 | Station 2 | Multipod |
| --- | --- | --- | --- | --- |
| LINE_001 | Leitung xy | XStationK_380 | StationA_380 | XStationK_380 |
| LINE_002 | Leitung xy | XStationK_380 | StationB_380 | XStationK_380 |
| LINE_003 | Leitung xy | XStationK_380 | StationC_380 | XStationK_380 |

Die Excel-Reihenfolge bestimmt die Rollen. Die Ausgabe in `mjap/Netzelemente.csv`
enthält genau drei Zeilen; folgende Tabelle kürzt die vollständigen Stations-IDs
zur besseren Lesbarkeit ab:

| MJAP-ID | Anfang | Ende | T-1 | Y1 | Leitungsname |
| --- | --- | --- | --- | --- | --- |
| Amprion_LINE_001 | A | B | C | X | Leitung xy |
| Amprion_LINE_002 | A | C | leer | leer | Leitung xy (ohne Bein StationB_380) |
| Amprion_LINE_003 | B | C | leer | leer | Leitung xy (ohne Bein StationA_380) |

`Station T-2` und `Y-Knoten-2` bleiben einschließlich ihrer ID-Spalten leer.
X steht nur im ersten Netzelement-Eintrag und einmal als Station in
`mjap/Stationen.csv`. IDs und übrige Attribute bleiben an ihren Excel-Zeilen.
Die Verbindungsbedeutung der ursprünglichen Bein-IDs ändert sich entsprechend
der Tabelle. Unterschiedliche Betriebsdaten oder eine andere Excel-Reihenfolge
müssen deshalb fachlich geprüft werden.

## Konvertierung wiederholen

Im Parser-Repository:

```bash
.venv/bin/python converter.py docs/beispiel/dreibein/DUMMY_Dreibein.xlsx --mjap \
  --freischaltungen docs/beispiel/dreibein/QUELLE_Freischaltungen.csv \
  --projekte docs/beispiel/dreibein/QUELLE_Projekte.csv \
  -o output/dreibein-demo/mjap
```

Im benachbarten MJAP-Repository:

```bash
../parser/.venv/bin/python ../parser/converter.py docs/beispiel/dreibein/DUMMY_Dreibein.xlsx --mjap \
  --freischaltungen docs/beispiel/dreibein/QUELLE_Freischaltungen.csv \
  --projekte docs/beispiel/dreibein/QUELLE_Projekte.csv \
  -o demo/dreibein-demo/mjap
```

Für den Import in QGIS den generierten CSV-Ordner in MJAP über
**Visualisierung erstellen** wählen und einen neuen vorhandenen Ausgabeordner
angeben. Als direkte Demonstration kann `docs/beispiel/dreibein/mjap` gewählt
werden. Keine manuelle Bearbeitung der CSVs ist erforderlich.

Freischaltungen und Projekte benötigen weiterhin zusätzliche Eingaben. Diese
Beispiele ersetzen nicht die noch ausstehende Verarbeitung weiterer Excel-Blätter.

## Erwartetes Ergebnis im unveränderten MJAP

| Layer | Features / Geometrien |
| --- | --- |
| Standorte | 4 Punkte: A, B, C, X |
| Stromkreise | 5 Linien: A–X, B–X, C–X, direkt A–C, direkt B–C |
| Standorte Schaltungen | 0: die Beispielschaltung betrifft eine Leitung, keinen Trafo |
| Stromkreise Schaltungen | 1 MultiLineString mit allen drei Y-Beinen |
| Standorte Projekte | 1 MultiPoint mit A, B und C |
| Stromkreise Projekte | 1 MultiLineString mit allen drei Y-Beinen |

Die Schaltung referenziert `Amprion_LINE_001` und betrifft daher das vollständige
Y. Die beiden Paarlinien gehören nicht zu dieser Schaltung. Ihre Geometrien
verlaufen direkt zwischen den äußeren Stationen, nicht über X.

Der vollständige Test prüft die fünf Shape-IDs, alle fünf Stationspaare,
Namensattribute, gültige Geometrien, die drei Teilstrecken der Schaltungs- und
Projektgeometrie, Zeitfelder und aktive Regelausdrücke. `PRUEFERGEBNIS.json`
enthält den tatsächlichen Assistentenlauf mit QGIS 3.40.3 und pandas 2.2.3.
Keine GUI-Warnung und keine kritische Meldung; unbekanntes ABN verursacht
weiterhin die bekannte pandas-Warnung zur Datumsformaterkennung.

Vier Beine an einem einzigen X werden nicht automatisch unterstützt. Das
bestehende Plugin verlangt für seine Doppel-Y-Topologie zwei virtuelle Knoten.
