# MJAP-kompatible CSVs und zusätzliche Länderkarten

Der MJAP-Plugin-Code bleibt unverändert. Die Anpassungen betreffen den Parser
und ein separates Werkzeug, das Länderlayer in eine Kopie eines QGIS-Projekts
einfügt. Die Ländererweiterung benötigt keine zusätzlichen Excel-Netzdaten.

## CSV-Konvertierung

```bash
.venv/bin/python converter.py input.xlsx --mjap \
  --freischaltungen Freischaltungen.csv --projekte Projekte.csv \
  -o output/mjap
```

Ohne `--mjap` bleibt die bisherige Konvertierung mit zwei CSV-Dateien unverändert.
Der neue Modus validiert strikt und liefert genau die benötigten Tabellen:

| Datei | Verhalten im MJAP-Modus |
| --- | --- |
| `Stationen.csv` | Unveränderte 20 Spalten; UTF-8 mit BOM; Koordinaten mit Dezimalkomma |
| `Netzelemente.csv` | Unveränderte 30 Spalten; `TRA` wird exakt zu `Trafo`; unbenutzte Topologiereferenzen bleiben leer |
| `Freischaltungen.csv` | Übernommene, nicht leere CSV mit echten Datensätzen |
| `Projekte.csv` | Übernommene, nicht leere CSV mit echten Datensätzen |

Der Parser erzeugt keine fiktiven Schaltungen, Projekte, Betriebsdaten oder
Koordinaten. Beispiel- und Testdaten sind ausdrücklich Dummy-Daten.

Vorhandene Schaltungs- und Projektexporte sind für den vollständigen MJAP-Modus erforderlich:

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

### Grenzen des unveränderten Assistenten

Die vollständige Prüfung hat eine Einschränkung der Excel-Zwischentabellen
aufgedeckt: Kopfzeilen ohne Daten werden vom installierten GDAL/XLSX-Treiber als
Datensätze mit `Field1`, `Field2`, … gelesen. MJAP bricht dadurch bei leeren
Freischaltungen mit `KeyError: Standort_von` ab. Auch vollständig fehlende
Betriebsdaten können die automatische Kopfzeilenerkennung verhindern und damit
Join-, Stil- und Zeitfelder beschädigen. `OGR_XLSX_HEADERS=FORCE` hat den Fall mit
nur einer Kopfzeile in dieser Umgebung **nicht** behoben.

Deshalb liefert `--mjap` jetzt ausschließlich vorab geprüfte, befüllte Viererpakete:

- `--freischaltungen` und `--projekte` müssen jeweils mindestens einen echten
  Datensatz enthalten. Fehlende oder leere Begleittabellen werden vor dem
  Schreiben abgewiesen. Die frühere Ausgabe leerer Vorlagen war nur im
  CSV-Konverter geprüft und ist für den vollständigen Assistenten zurückgenommen.
- Der abgesicherte Modus verlangt ein gültiges IBN-Datum je Station und
  Netzelement. ABN darf unbekannt bleiben. Diese strengere Vorgabe verhindert
  die beobachtete Kopfzeilenfehlinterpretation ohne erfundene Termine.
- Leitungsenden mit identischen Koordinaten werden abgewiesen. Auch verschiedene
  Stations-IDs lösen das Problem der Null-Länge im Geometrieexport nicht.
- IDs müssen im CP1252-Shapefile verlustfrei darstellbar sein und dürfen höchstens
  254 Bytes lang sein. Steuerzeichen und Ausdruckstrennzeichen sind nicht erlaubt.
- Doppelte CSV-Kopfzeilen und intern erzeugte Schaltungsspalten, z. B.
  `MJAP-ID_Schaltung`, `Element Typ`, `Standort_von`, werden abgewiesen.
- Elemente mit fehlenden Pflichtreferenzen dürfen nicht aus dem Export verschwinden.
  Unbekannte Verweise, umgekehrte Datumsbereiche, leere IDs und doppelte
  Schaltungs-/Projektkennungen werden ebenfalls abgewiesen.

Die vier Dateien werden zunächst vollständig in einem temporären Unterordner
serialisiert. Ein normaler Schreib- oder Veröffentlichungsfehler stellt das
vorherige Paket wieder her. Das ist keine Transaktion bei Prozessabbruch oder
für gleichzeitig lesende Programme: MJAP erst nach beendetem Export starten.

Bei vollständig unbekanntem ABN kann der unveränderte Plugin-Code eine pandas-
Warnung zur Datumsformaterkennung ausgeben. Die Tests prüfen, dass daraus kein
Importfehler entsteht. Die frühere Warnung zur Zuweisung von Text in numerische
Datumsfelder wird durch passende CSV-Textwerte vermieden. Eine Garantie für
beliebige Eingaben, beliebige Plugin-Einstellungen oder andere Bibliotheksversionen
ist damit nicht verbunden.

Ohne `--mjap` bleibt der allgemeine Zwei-Tabellen-Export einschließlich seiner
bisherigen Regeln erhalten; er ist nicht als geprüftes Assistentenpaket anzusehen.

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
  python -m pytest tests/testMjap.py tests/testMjapQgis.py tests/testMjapWizard.py
```

Alternativ aus dem Parser-Ordner: `bash scripts/test_mjap.sh`.

Die Tests prüfen CSV → MJAP → CSV/XLSX, die Abweisung leerer Tabellen,
Datumserhalt, Transformatorzuordnung, Multipod-Beine sowie die Länder-Geometrien
und den Erhalt vorhandener Kartenlayer. Drei zusätzliche, isolierte Prozesse
führen den vollständigen Visualisierungsassistenten aus und prüfen Shapefile-
und GeoPackage-Geometrien, Attribut-/Projektverknüpfungen, Feldnamen der zeitlichen
Darstellung und aktive QGIS-Regelausdrücke. GUI-Warnungen werden aufgezeichnet
und führen zum Testfehler; sie werden nicht still verworfen.

Ergebnisse und Details: [MJAP_PRUEFBERICHT_DE.md](MJAP_PRUEFBERICHT_DE.md).
Treiberkonfiguration: [offizielle GDAL/XLSX-Dokumentation](https://gdal.org/en/stable/drivers/vector/xlsx.html).
