# MJAP-kompatible CSVs und zusätzliche Länderkarten

Der MJAP-Plugin-Code bleibt unverändert. Die Anpassungen betreffen den Parser
und ein separates Werkzeug, das Länderlayer in eine Kopie eines QGIS-Projekts
einfügt. Die Ländererweiterung benötigt keine zusätzlichen Excel-Netzdaten.

## CSV-Konvertierung

```bash
.venv/bin/python converter.py input.xlsx --mjap -o output/mjap
```

Ohne `--mjap` bleibt die bisherige Konvertierung mit zwei CSV-Dateien unverändert.
Der neue Modus validiert strikt und liefert genau die benötigten Tabellen:

| Datei | Verhalten im MJAP-Modus |
| --- | --- |
| `Stationen.csv` | Unveränderte 20 Spalten; UTF-8 mit BOM; Koordinaten mit Dezimalkomma |
| `Netzelemente.csv` | Unveränderte 30 Spalten; `TRA` wird exakt zu `Trafo`; unbenutzte Topologiereferenzen bleiben leer |
| `Freischaltungen.csv` | Übernommene echte CSV oder leere Tabelle mit den benötigten Überschriften |
| `Projekte.csv` | Übernommene echte CSV oder leere Tabelle mit den benötigten Überschriften |

Der Parser erzeugt keine fiktiven Schaltungen, Projekte, Betriebsdaten oder
Koordinaten. Beispiel- und Testdaten sind ausdrücklich Dummy-Daten.

Bereits vorhandene Schaltungs- und Projektexporte können mitgegeben werden:

```bash
.venv/bin/python converter.py input.xlsx --mjap \
  --freischaltungen Freischaltungen.csv --projekte Projekte.csv \
  -o output/mjap
```

Die CSV-Eingaben müssen UTF-8 und komma-getrennt sein. Datumswerte haben das Format
`TT.MM.JJJJ`. Schaltungen referenzieren die vom Parser erzeugten Netzelement-MJAP-IDs
(`TSO_ELEMENT ID`), Projekte deren Stations-MJAP-IDs. Datumsbereiche, Referenzen und
eindeutige Projektnamen werden vor dem Schreiben geprüft. Leerzeichen nach Kommas
in Projekt-Standortlisten werden entfernt, damit MJAP die IDs korrekt verknüpft.

### Warum der eigene Ausgabemodus nötig ist

MJAP liest CSVs mit `pandas.read_csv(..., decimal=',')`, erkennt Anschlüsse mit
`notna()` und verarbeitet Mehrfachtermine mit `.str.split()`.

Ein allgemeiner Leerzeichen-Platzhalter würde bei `Station T-1:MJAP-ID` und
`Station T-2:MJAP-ID` zusätzliche Anschlüsse vortäuschen. Wirklich leere
Mehrfachterminspalten würden hingegen als numerisch erkannt und `.str` würde
abbrechen. Der neue Modus löst beides getrennt:

- Unbenutzte Topologiefelder werden als echte leere CSV-Zellen ausgegeben.
- Die Mehrfachterminfelder wiederholen die bereits vorhandenen IBN-/ABN-Termine
  als Einzellisten. Nur ein fehlender Termin erhält dort ein Leerzeichen, damit
  die Spalte Text bleibt; beim MJAP-Datumsparser bleibt dieser Termin leer.
- `TRA` muss `Trafo` heißen, da MJAP nur dann die Transformator-Schaltung räumlich
  dem Standort zuordnet. Umbenennungen der Vertrags-Spalten werden im MJAP-Modus
  abgewiesen; ebenso eine abweichende Transformatorübersetzung.
- Verweise auf nicht vorhandene Stationen, doppelte MJAP-IDs, identische Endpunkte
  und IDs mit für MJAP-Ausdrücke problematischen Trennzeichen werden abgewiesen.

Die mitgelieferte allgemeine `targetFormat.example.json` übersetzt `TRA` zu
`Transformator` und ist deshalb bewusst **nicht** mit `--mjap` kombinierbar.

Die Kompatibilität wurde mit dem tatsächlichen MJAP-Konverter und dessen lokaler
QGIS-3.40-/pandas-2.2-Umgebung geprüft. Die Umgebung ist in `mjap_plugin/environment.yml`
definiert. Eine Portierung des Plugin-Codes auf pandas 3 ist damit nicht zugesichert.

## Niederlande, Belgien und Frankreich in der Karte

Die mitgelieferten Ländergrenzen umfassen **DE, NL, BE und FR**. Sie stammen aus
Natural Earth v5.1.2, Maßstab 1:50 Mio., und stehen unter Public Domain. Das sind
echte Offline-Kartendaten. Überseegebiete werden aus der europäischen Übersicht
entfernt. Deutschland bleibt als Kontext enthalten.

Zuerst den normalen MJAP-Visualisierungsassistenten ausführen und das Projekt
speichern. Danach die Länder ergänzen:

```bash
micromamba run -p ../mjap_plugin/.local-env \
  python -m excelToCsv.mapProject \
  --project ../mjap_plugin/demo/output/MJAP-Demo.qgz \
  --output output/karte/MJAP-Laender.qgz \
  --countries DE NL BE FR
```

Für Micromamba bitte einen absoluten Umgebungspfad verwenden, falls die lokale
Version relative `-p`-Pfade nicht unterstützt. Alternativ ist das nachfolgende
Skript dafür vorgesehen:

```bash
bash scripts/country_map.sh \
  --project ../mjap_plugin/demo/output/MJAP-Demo.qgz \
  --output output/karte/MJAP-Laender.qgz
```

Das Werkzeug erzeugt `Laender.gpkg` mit einem eigenen Layer je Land sowie das neue
QGIS-Projekt. Vorhandene Netz-, Schaltungs- und Projektlayer bleiben erhalten.
Die ursprüngliche Projektdatei wird nicht überschrieben. Derselbe Vorgang kann
erneut ausgeführt werden; die eigene Ländergruppe wird ersetzt statt dupliziert.

Ohne `--project` entsteht eine reine Länderkarte. `--countries NL BE FR` beschränkt
die Auswahl. Eine lokale Kartenansicht lässt sich mit
`--preview output/karte/Uebersicht.png` exportieren.

### Optional: Straßen- und Ortsnamenkarte

`--osm` ergänzt einen Online-Layer mit OpenStreetMap-Kacheln. Die Ländergrenzen
bleiben lokal. OpenStreetMap benötigt Internet; die Quellenangabe wird im Projekt
aktiviert. Es werden keine Kacheln für Offline-Nutzung gesammelt. `--preview`
wird deshalb nur ohne `--osm` unterstützt.

Der MJAP-Assistent blendet unbekannte Layer bei seiner Stilanwendung aus.
**Die Länderkarte deshalb nach dem Assistenten ergänzen.** Wird der Assistent
später erneut ausgeführt, die Ländergruppe anschließend im Layerbaum wieder
einschalten oder das Kartenwerkzeug erneut ausführen. Dafür ist keine Änderung
am MJAP-Plugin erforderlich.

Quellen: [Natural Earth](https://www.naturalearthdata.com/downloads/50m-cultural-vectors/50m-admin-0-countries-2/),
[Lizenz](https://www.naturalearthdata.com/about/terms-of-use/),
[OpenStreetMap-Attribution](https://www.openstreetmap.org/copyright),
[Kachelregeln](https://operations.osmfoundation.org/policies/tiles/).
Die heruntergeladenen Geometrien und die Herkunft sind in `excelToCsv/maps` enthalten.

## Tests

```bash
.venv/bin/python -m pytest
```

Ohne QGIS wird nur das optionale Integrationsmodul übersprungen. Mit der
QGIS-Umgebung lassen sich die echten Verbrauchertests zusätzlich ausführen:

```bash
micromamba run -p /ABSOLUTER/PFAD/mjap_plugin/.local-env \
  python -m pytest tests/testMjapQgis.py
```

Die Verbrauchertests prüfen CSV → MJAP → CSV/XLSX, leere und befüllte
Schaltungs-/Projekttabellen, Datumserhalt, Transformatorzuordnung, Multipod-Beine
sowie die Länder-Geometrien und den Erhalt vorhandener Kartenlayer.
