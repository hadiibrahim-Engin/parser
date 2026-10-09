# Durchgehendes Dummy-Beispiel

**Alle Dateien hier enthalten ausschließlich Dummy-Daten.** Die Beispiele dienen
der Erklärung des Datenvertrags und stellen keine realen Netzdaten dar.

Das zusätzliche [Excel-Dreibein-Beispiel](dreibein/README_DE.md) zeigt die neue
Regel: ein vollständiger Y-Eintrag und zwei Paarverbindungen, nur einmal Y1.

| Datei | Rolle |
| --- | --- |
| `DUMMY_Netz.xlsx` | Excel-Eingabe des Parsers; ein Blatt mit zwei Stationen, einer Leitung und einem Transformator |
| `QUELLE_Freischaltungen.csv` | Zusätzliche echte Struktur mit einem Dummy-Schaltungsdatensatz |
| `QUELLE_Projekte.csv` | Zusätzliche echte Struktur mit einem Dummy-Projekt für zwei Stationen |
| `mjap/Stationen.csv` | Geprüfte Parser-Ausgabe mit allen 20 Spalten |
| `mjap/Netzelemente.csv` | Geprüfte Parser-Ausgabe mit allen 30 Spalten |
| `mjap/Freischaltungen.csv` | Geprüfte übernommene Schaltungstabelle mit den Stilspalten |
| `mjap/Projekte.csv` | Geprüfte übernommene Projekttabelle |
| `PRUEFERGEBNIS.json` | Nachweis des vollständigen MJAP-Assistentenlaufs mit Feldnamen, Mengen und aufgezeichneten Meldungen |

## Konvertierung wiederholen

Aus dem Parser-Repository, in dem dieses Handbuch ebenfalls liegt:

```bash
.venv/bin/python converter.py docs/beispiel/DUMMY_Netz.xlsx --mjap \
  --freischaltungen docs/beispiel/QUELLE_Freischaltungen.csv \
  --projekte docs/beispiel/QUELLE_Projekte.csv \
  -o output/handbuch-demo/mjap
```

Im MJAP-Repository lautet derselbe Aufruf, wenn beide Projekte benachbart liegen:

```bash
../parser/.venv/bin/python ../parser/converter.py docs/beispiel/DUMMY_Netz.xlsx --mjap \
  --freischaltungen docs/beispiel/QUELLE_Freischaltungen.csv \
  --projekte docs/beispiel/QUELLE_Projekte.csv \
  -o demo/handbuch-demo/mjap
```

Für die direkte Demonstration kann alternativ der bereits erzeugte Ordner
`docs/beispiel/mjap` im MJAP-Menü **Visualisierung erstellen** als Eingabeordner
ausgewählt werden. Als Ausgabeordner einen neuen, vorhandenen Ordner verwenden.
Das bereitgestellte Paket soll dabei nicht nachträglich editiert werden.

Erwartete Layer-Mengen:

| Layer | Features |
| --- | --- |
| Standorte | 2 |
| Stromkreise | 2 |
| Standorte Schaltungen | 1 |
| Stromkreise Schaltungen | 1 |
| Standorte Projekte | 1 MultiPoint mit zwei enthaltenen Punkten |
| Stromkreise Projekte | 1 |

Geprüft in QGIS 3.40.3 / pandas 2.2.3. Die bekannten ABN sind in diesem Beispiel
nicht vorhanden und bleiben leer. Der unveränderte Plugin-Code gibt deshalb
eine bekannte pandas-Warnung zur Datumsformaterkennung aus. Im aufgezeichneten
Assistentenlauf gab es keine GUI-Warnung, keine kritische Meldung und keine
Fehler in den geprüften aktiven Regelausdrücken. Virtuelle Zeitreihen mit
unbekanntem ABN haben die im Handbuch beschriebene zusätzliche Einschränkung.
