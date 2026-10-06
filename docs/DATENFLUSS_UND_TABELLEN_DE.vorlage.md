# Excel → Parser → CSV → MJAP → QGIS

## 1. Zweck und verlässlicher Stand

Dieses Handbuch erklärt die Ein- und Ausgaben beider Programme. Es beschreibt,
welche Spalten vorhanden sein müssen, welche Werte gebraucht werden, welche
Werte leer bleiben dürfen und welche Dateien das Plugin selbst erzeugt.
Stand: 06.10.2026; Parser auf `main` einschließlich der Dreibein-Regel,
MJAP-Codebasis `2594712`. Die Dreibein-Änderung betrifft ausschließlich den
Parser; die Plugin-Implementierung bleibt unverändert.

**Der gewünschte Ablauf lautet:** Excel einlesen, CSVs erzeugen, den CSV-Ordner
im MJAP-Menü von QGIS auswählen und die Daten visualisieren. QGIS lädt diese
Dateien lokal. Der Code stellt keine Verbindung zu einem SharePoint-Server
oder einer externen Datenbank her; „Sharepoint2QGIS“ ist der Name des Werkzeugs.

**Der derzeit vollständige Ablauf benötigt zusätzliche Schaltungs- und
Projektdaten:** Aus dem ausgewählten Excel-Blatt erzeugt der Parser nur
`Stationen.csv` und `Netzelemente.csv`. Im Modus `--mjap` übernimmt er zusätzlich
zwei vorhandene, befüllte CSVs für Schaltungen und Projekte. Er liest diese
derzeit nicht aus weiteren Excel-Blättern. Excel allein liefert daher aktuell
kein vollständiges Paket für den Visualisierungsassistenten.

<!-- FIG:ablauf -->

| Station des Ablaufs | Eingabe | Verarbeitung | Ausgabe / Übergabe |
| --- | --- | --- | --- |
| Excel-Bearbeitung | Fachliche Netzdaten | Stationen und Netzelemente mit IDs, Koordinaten und Terminen pflegen | Ein ausgewähltes Excel-Blatt |
| Parser | Excel; im MJAP-Modus zusätzlich echte Schaltungs-/Projekt-CSVs | Kopfzeilen erkennen, Werte normalisieren, Referenzen prüfen, feste Ausgabespalten erzeugen | Vier CSVs im MJAP-Exportordner |
| MJAP: Sharepoint2QGIS | Vier CSVs | Koordinaten und Topologie auswerten; Daten zusammenführen; Attribute aufbereiten | `SO.csv`, `SK.csv`, `attribute.xlsx`, `missing_data.xlsx` |
| MJAP: Visualisierung erstellen | Die genannten Zwischenprodukte | SpatiaLite erzeugt Geometrien; QGIS importiert Layer, Joins, Stile und Zeitfelder | Shapefiles, GeoPackages, QGIS-Layer |
| QGIS-Projekt speichern | Die importierten Layer | Projektdatei mit Verweisen auf Datendateien speichern | Eine vom Benutzer gespeicherte `.qgz`-Datei |
| Länder ergänzen | Gespeichertes Projekt, lokale Ländergrenzen | Separates Parser-Kartenwerkzeug | Projektkopie und Länder-GeoPackage |

## 2. Begriffe: Spaltenpflicht ist nicht Befüllpflicht

Eine **Pflichtspalte** muss als Überschrift existieren, auch wenn ihre Werte leer
bleiben dürfen. Ein **Pflichtwert** muss in der betreffenden Zeile ausgefüllt
sein. Ein **bedingter Pflichtwert** wird nur bei einer bestimmten Topologie
oder Darstellung gebraucht. Eine automatisch erzeugte Spalte wird vom Parser
oder vom Plugin gepflegt und soll nicht von Hand erfunden werden.

| Kennzeichen im Feldkatalog | Bedeutung | Was der Anwender tun soll |
| --- | --- | --- |
| P | Pflichtwert im abgesicherten Parser-/MJAP-Ablauf | Mit echten, gültigen Quelldaten befüllen |
| O | Optionaler Wert | Nur befüllen, wenn fachlich vorhanden; sonst leer lassen |
| S | Wert für die mitgelieferten Stile empfohlen bzw. erforderlich | Für die gewünschte sichtbare Darstellung befüllen; fehlender Wert muss keinen Importfehler erzeugen |
| A | Automatisch erzeugt | Quelle korrekt pflegen; das erzeugte Feld normalerweise nicht ändern |
| L | Vom aktuellen Parser ohne Quelle leer erzeugt | Leer lassen; keine IDs, Termine oder Region erfinden |
| B | Bedingt nötig beim direkten MJAP-Import | Nur für die betreffende Topologie vollständig befüllen |

`P` beschreibt hier den **MJAP-Netzexport (CLI-Standard) und `--mjap`**. Das unveränderte
Plugin validiert weniger konsequent und kann auch ungültige oder unvollständige
Daten annehmen, anschließend auslassen oder mit einer Fehlermeldung abbrechen.
Das ist keine Freigabe solcher Daten.

**CSV-Dateien speichern keine verbindlichen Datentypen.** Die Angaben „Text“,
„Dezimalzahl“ und „Datum“ in diesem Handbuch sind der logische Datenvertrag.
pandas und GDAL erkennen beim Einlesen die tatsächlichen Typen aus den Werten.
Deshalb sind leere Spalten, numerisch aussehende IDs und Listen besonders wichtig.

## 3. Excel-Eingabe: Aufbau des ausgewählten Blatts

Alle 13 folgenden Spalten müssen existieren. Das bedeutet nicht, dass jede
Zelle in jeder Zeile einen Wert enthalten muss. `SUB` bezeichnet eine Station;
alle anderen bekannten Typen werden als Netzelement behandelt.

<!-- TABLE:excel -->

Die **Stations-ELEMENT-ID ist im gesamten ausgewählten Blatt eindeutig**, auch
über mehrere TSO hinweg. Die Stationsreferenzen werden anhand dieser Roh-ID
aufgelöst. Zwei Stationen verschiedener Eigentümer mit derselben `ELEMENT ID`
werden daher nicht automatisch auseinandergehalten.

Empfohlene Stations-ID: `<Name>_<Spannung>`, z. B. `Berlin_380`. Eine abweichende
Benennung löst eine Warnung aus und kann einen Ersatznamen aus `LONG-NAME` und
`ELEMENT ID` erzeugen. Virtuelle Knoten werden am Präfix `X` des Stationsteils
erkannt, z. B. `XKnoten_380`; diese erhalten `reales UW = Falsch`.

### 3.1 Optionale und nicht übernommene Excel-Spalten

<!-- TABLE:excel_optional -->

Zusätzliche, unbekannte Excel-Spalten werden nicht automatisch als zusätzliche
CSV-Spalten ausgegeben. Das Ergebnis ist eine fachliche Abbildung auf ein festes
Schema, keine verlustfreie Kopie der gesamten Arbeitsmappe.

### 3.2 Ein Blatt auswählen und Kopfzeilen finden

Ohne `--sheet` wird nur das erste Blatt gelesen. Ein Blattname oder ein nullbasierter
Index kann mit `--sheet` ausgewählt werden. Die Kopfzeile wird automatisch erkannt;
Zeilen davor sind Vorspann und werden nicht als Netzdaten übernommen.
`--header-row 4` legt beispielsweise Excel-Zeile 4 als Kopfzeile fest.
Bekannte Eingabeüberschriften werden hinsichtlich Groß-/Kleinschreibung und
Leerraum normalisiert; doppelte Überschriften nach Normalisierung sind unzulässig.
Vollständig leere Datenzeilen werden übersprungen.

### 3.3 Datums-, Koordinaten- und Spannungsregeln

- Excel-Datumswerte und Formate wie `2025-05-09`, `09.05.2025`, `09/05/2025`,
  `2025/05/09`, `09-05-2025` oder `20250509` werden auf `09.05.2025` normalisiert.
  Bei Datumswerten mit Uhrzeit bleibt im Ergebnis nur das Datum erhalten.
- Numerische Excel-Datumswerte werden als Seriennummern des 1900-Datumssystems
  interpretiert. Ein abweichendes Datumssystem darf nicht ungeprüft vorausgesetzt werden.
- Der Standard-Netzexport und `--mjap` verlangen eine gültige IBN pro Station und Netzelement. ABN darf fehlen;
  bei bekannten IBN/ABN muss IBN ≤ ABN gelten. Keine fehlenden Termine erfinden.
- Koordinaten sind Breitengrad/Längengrad in WGS84, nicht Rechts-/Hochwerte eines
  projizierten Systems. Breitengrad: −90 bis 90; Längengrad: −180 bis 180.
- Excel-Koordinaten dürfen Punkt oder Komma als Dezimalzeichen haben.
  Der Parser kann fehlende Dezimalzeichen anhand der Spalte rekonstruieren oder
  schätzen und protokolliert dies als Warnung. **Reparierte Koordinaten fachlich
  prüfen**; ein numerisch gültiger Wert beweist keinen korrekten Standort.
- `380.0/110.0` wird bei Stationen zu `['380','110']` als JSON-Text mit doppelten
  Anführungszeichen und bei Netzelementen zu `380/110` als Text.
- Der historische Parser-Modus `--legacy` unterstützt semikolongetrennte Datumswerte. Der geprüfte
  MJAP-Modus dieses Parsers ist auf **einzelne IBN-/ABN-Termine pro Datensatz**
  ausgelegt. Mehrfachtermine gehören nicht zum freigegebenen Excel-Exportweg.
  Eine mehrteilige ABN wird aktuell nicht in jedem Fall vor dem Schreiben
  abgefangen; mehrere ABN bei einer IBN können später `explode()` abbrechen.

## 4. Parser-Modi und Exportvertrag

| Modus | Ausgabe | Fehlerverhalten / Zweck |
| --- | --- | --- |
| CLI-Standard: Excel + `-o` | Zwei CSVs mit 20 bzw. 30 Spalten | MJAP-Netzformat; strikte Validierung; UTF-8-BOM, Dezimalkomma, echte leere T-/Y-Zellen, passende Mehrfachdatumsfelder |
| `--legacy` | Zwei CSVs im historischen Format | Fehlertolerant, allgemeine Leerzeichen-Platzhalter; nicht als MJAP-Eingabe verwenden |
| `--legacy --strict` | Zwei historische CSVs | Fehler führen zum Abbruch; das historische Format wird dadurch nicht MJAP-kompatibel |
| `--mjap` | Vier CSVs, sofern alle Voraussetzungen erfüllt sind | Strikte Validierung; feste Überschriften; kompatible Typübersetzung und Leerwertbehandlung |

Der historische Modus `--legacy` füllt vollständig leere Spalten mit einem
Leerzeichen. Für Topologiereferenzen ist das im Plugin gefährlich: `notna()`
erkennt ein Leerzeichen als vorhandenen Anschluss. Beide MJAP-Exporte verwenden deshalb
echte leere Zellen für unbenutzte Topologie und spezielle Textwerte nur bei
fehlenden Datumswerten der Netzelemente.

**Ein Excel-Netzblatt genügt für die beiden Netztabellen:**

```bash
.venv/bin/python converter.py "input.xlsx" -o "output/mjap" --details
```

Unter Windows mit dem Python-Interpreter der installierten Parser-Umgebung:

```powershell
python converter.py "C:\Daten\input.xlsx" -o "C:\Daten\output" --details
```

Der Aufruf erzeugt ausschließlich `Stationen.csv` und `Netzelemente.csv`.
Keine manuelle CSV-Nachbearbeitung und keine Begleit-CSV als Eingabe sind für
diesen Export nötig. Vorhandene Freischaltungen/Projekte im Ausgabeordner werden
nicht verändert. **Der vollständige Plugin-Assistent braucht weiterhin alle
vier Tabellen mit echten Schaltungs-/Projektdaten.** Ein Ordner mit nur zwei
Dateien ist daher noch kein vollständiges Assistentenpaket.

Die Python-API behält aus Kompatibilitätsgründen ihr historisches Verhalten:
`runConversion(..., mjapNetwork=True)` wählt ausdrücklich den sicheren
Zwei-Tabellen-Export; `mjap=True` das Viererpaket. Bei Validierungsfehlern bleibt
der vorherige Export erhalten; nicht versehentlich alte Dateien importieren.

Die allgemeine `targetFormat.example.json` ist für MJAP nicht automatisch
geeignet: dort kann `TRA` anders übersetzt werden. Im MJAP-Modus sind
Spaltenumbenennungen und eine abweichende Zuordnung `TRA → Trafo` verboten.
Die Standardzuordnungen lauten `LINE → Stromkreis`, `TRA → Trafo`,
`TIE → Kuppelleitung`, `DCL → HGÜ-Strecke`; weitere Typen bleiben ohne eigene
zulässige Zuordnung bei ihrem Code.

### 4.1 Gemeinsame CSV-Regeln für den Plugin-Eingabeordner

| Eigenschaft | Vorgabe |
| --- | --- |
| Dateinamen | Exakt `Stationen.csv`, `Netzelemente.csv`, `Freischaltungen.csv`, `Projekte.csv` |
| Ablage | Alle vier Dateien im selben Eingabeordner |
| Encoding im MJAP-Modus | UTF-8 mit BOM; Schaltungs-/Projektquellen ebenfalls UTF-8 |
| Spaltentrenner | Komma, nicht Semikolon |
| Dezimalzeichen für Stationskoordinaten | Komma |
| Datumswerte | `TT.MM.JJJJ`, z. B. `01.06.2028` |
| Listen / Zahlen mit Komma | CSV-gerecht als ein Feld in doppelten Anführungszeichen |
| Zeilen / Überschriften | Keine doppelten Spalten; keine zusätzlichen Überschriftenzeilen zwischen Daten |
| Leerwert | Eine echte leere Zelle, außer ausdrücklich beschriebenen Parser-Datumssentinels |
| IDs | Stabile Textkennungen; vorzugsweise mit Buchstabenpräfix, keine ausschließlich numerischen Kennungen mit führenden Nullen |

Im abgesicherten Modus sind Stations- und Netzelement-IDs eindeutig, nicht leer,
CP1252-kompatibel und höchstens 254 Bytes lang. Nicht erlaubt sind Anführungszeichen,
Komma, Semikolon, Backslash oder Steuerzeichen. Diese Einschränkung ergibt sich
aus Ausdrucksverarbeitung und dem CP1252-Shapefile-Export des Plugins.
Umlaute sind nicht pauschal verboten. Numerisch aussehende Schaltungs-/Projekt-IDs
können durch Typinferenz verändert werden; Textkennungen wie `FS_001` und
`Projekt_A` vermeiden dieses Risiko. Der Parser prüft nicht jede mögliche
Typinferenz eines fremden, manuell erweiterten CSV-Exports.

## 5. Stationen.csv – alle 20 Ausgabespalten

Alle 20 Überschriften gehören zum Parser-Vertrag und bleiben erhalten.
„Plugin liest“ bezeichnet den direkten Zugriff des aktuellen Sharepoint2QGIS-
Konverters; „nein“ bedeutet nicht, dass die Spalte aus der Parser-Ausgabe entfernt
werden soll. Die meisten Felder werden automatisch aus Excel abgeleitet.

<!-- TABLE:stations -->

Die Stationen erhalten bei `Spannung` beispielsweise den logischen JSON-Text
`["380","110"]`. Im echten CSV wird dieser Text mit CSV-Escaping gespeichert:

```csv
Spannung
"[""380"",""110""]"
```

## 6. Netzelemente.csv – alle 30 Ausgabespalten

Alle 30 Überschriften gehören zum Parser-Vertrag. **Ein leerer Wert in einem
optionalem Anschlussfeld ist zulässig; eine fehlende Überschrift ist es für die
direkt gelesenen Felder nicht.** Die einfachen Anschlussfelder und die
`:MJAP-ID`-Felder sind im Parser-Ausgang bereits auf die vollständigen Stations-IDs
aufgelöst; es stehen dort nicht mehr nur die Excel-Roh-IDs.

<!-- TABLE:elements -->

### 6.1 Multipod im Parser und Y-Topologie im Plugin

<!-- FIG:topologie -->

**Excel ist die Eingabe; die CSVs werden ohne manuelle Nachbearbeitung erzeugt.**
Ein Dreibein benötigt vier `SUB`-Zeilen (A, B, C und den virtuellen Knoten X)
und drei Leitungszeilen. Jede Leitungszeile verbindet X mit genau einer anderen
Station und enthält dieselbe Roh-ID von X in `Multipod`. Die Richtung
`Station 1` / `Station 2` darf umgekehrt sein. X braucht eigene Koordinaten;
der Parser erzeugt weder den Knoten noch dessen Position.

Die **Reihenfolge der drei Leitungszeilen im Excel-Blatt** legt A, B und C fest.
Die erste Zeile wird zum vollständigen Y-Eintrag, die zweite zu A–C und die
dritte zu B–C. Es bleiben drei CSV-Zeilen; keine vierte Sammelzeile wird ergänzt.

| CSV-Zeile / Excel-Quellzeile | Anfang | Ende | T-1 | T-2 | Y-Knoten-1 | Leitungsname |
| --- | --- | --- | --- | --- | --- | --- |
| Erste Leitungszeile | A | B | C | leer | X | `LONG-NAME` der ersten Excel-Zeile |
| Zweite Leitungszeile | A | C | leer | leer | leer | `LONG-NAME` der zweiten Zeile + ` (ohne Bein <Roh-ID von B>)` |
| Dritte Leitungszeile | B | C | leer | leer | leer | `LONG-NAME` der dritten Zeile + ` (ohne Bein <Roh-ID von A>)` |

Anfang, Ende und T-1 werden in den normalen und den `:MJAP-ID`-Spalten mit den
vollständigen Stations-IDs gefüllt. Y1 enthält einmal die Roh-ID und einmal
deren vollständige MJAP-ID. **Nur die erste Netzelementzeile trägt den Y-Knoten.**
In `Stationen.csv` steht X einmal als eigener Stationseintrag. T-2 und Y2
bleiben bei allen drei Datensätzen leer. Lang- und Kurzname erhalten dieselben
Zusätze; IDs, Eigentümer, Termine und übrige Attribute bleiben ihrer jeweiligen
Excel-Quellzeile zugeordnet. Deshalb verändern eine andere Excel-Reihenfolge
oder unterschiedliche Betriebsdaten der Beine auch die Zuordnung des vollständigen
Y-Eintrags. Diese fachliche Zuordnung muss in Excel bewusst gepflegt werden.

MJAP erzeugt aus dem ersten Eintrag drei Strecken A–X, B–X und C–X; aus den
anderen beiden je eine **direkte** Linie A–C und B–C. Die Paarlinien verlaufen
nicht über X. Insgesamt sind es fünf Linienobjekte mit drei Netzelement-IDs.
Eine Freischaltung der ersten ID betrifft alle drei Y-Beine; die anderen IDs
betreffen jeweils nur ihre Paarlinie. Die ursprünglichen Bein-IDs werden
beibehalten, ihre Verbindungsbedeutung ändert sich jedoch gemäß dieser Tabelle.

Eine Gruppe benötigt genau drei verschiedene äußere Stationen, dieselbe Spannung
und denselben Leitungstyp (`LINE`, `TIE` oder `DCL`). Fehlende Beine, doppelte
Endpunkte, mehrere Stromkreise am gleichen Multipod oder vier Beine werden als
Fehler gemeldet. Der Standardexport und `--mjap` brechen vor dem Schreiben ab;
`--legacy` ohne `--strict` protokolliert den Fehler. Vier Beine an einem einzigen X
werden derzeit nicht automatisch konvertiert: T-2 allein genügt im bestehenden
Plugin nicht, weil dessen Doppel-Y-Topologie zwei Y-Knoten verlangt.

Ein vollständiges [Excel-Dreibein-Beispiel](beispiel/dreibein/README_DE.md)
zeigt Eingabe, automatisch erzeugte CSVs und den echten MJAP-Prüflauf.

Der direkte MJAP-Import kann außerdem eine zusammengefasste Y-Zeile aufspalten:

| Topologie im direkten MJAP-Eingang | Belegte Referenzen | Anzahl erzeugter Teilstrecken |
| --- | --- | --- |
| Punkt zu Punkt | Anfang, Ende; T1/T2 leer | 1 |
| Y | Anfang, Ende, T1, Y1; T2 leer | 3 |
| Doppel-Y | Anfang, Ende, T1, T2, Y1, Y2 | 5 |

Die sechs referenzierten Felder heißen exakt `Station Anfang:MJAP-ID`,
`Station Ende:MJAP-ID`, `Station T-1:MJAP-ID`, `Station T-2:MJAP-ID`,
`Y-Knoten-1: MJAP-ID`, `Y-Knoten-2: MJAP-ID`. Bei Y-Feldern steht ein Leerzeichen
nach dem Doppelpunkt; bei Stationsfeldern nicht. Alle belegten IDs müssen in
`Stationen.csv` mit gültigen Koordinaten vorkommen. Der Parser befüllt die
Y-Topologie nach der oben beschriebenen Dreibein-Regel automatisch.

### 6.2 Mehrfachtermine beim direkten Plugin-Import

<!-- FIG:zeit -->

MJAP spaltet `IBN - Mehrfach` und `ABN - Mehrfach` paarweise auf, getrennt durch
Komma oder Semikolon. Beide Listen müssen pro Zeile gleich lang sein. Vorhandene
Listenwerte überschreiben für die betreffende Phase die einfachen IBN-/ABN-Werte.
Die Phasen werden pro ursprünglicher ID stabil nach Terminen sortiert; die erste
behält die ID, weitere erhalten `_1`, `_2`, … . Schaltungen können anhand ihres
Zeitfensters einer späteren Phase zugeordnet werden.

Im freigegebenen Parser-MJAP-Weg werden einzelne Termine als Einzellisten
ausgegeben. Fehlendes ABN wird bei
Netzelementen in `ABN` und `ABN - Mehrfach` als ein Leerzeichen serialisiert.
Das ist **kein** Ausbaudatum: der Plugin-Datumsparser macht daraus einen fehlenden
Wert. Nicht selbst ein Platzhalterdatum wie `31.12.2099` einsetzen, nur um eine
Warnung oder einen leeren Wert zu vermeiden.

## 7. Freischaltungen.csv – Schaltungsdaten als zusätzliche Quelle

Im Modus `--mjap` muss diese Quelltabelle mindestens einen echten Datensatz
enthalten. Die ersten sechs Spalten sind als Überschriften erforderlich;
der Parser ergänzt die drei Stilfelder bei Bedarf leer. Für sinnvolle
Standarddarstellungen sollen die betreffenden Stilwerte fachlich gepflegt werden.

<!-- TABLE:outages -->

Die drei IDs haben verschiedene Aufgaben: `MJAP-ID` identifiziert die Schaltung,
`interne ID` wird zur automatisch erzeugten `MJAP-ID_Schaltung`, und
`Netzelement:MJAP-ID` identifiziert die Leitung oder den Transformator. Sie dürfen
nicht miteinander verwechselt werden. Gleichsetzen von `MJAP-ID` und `interne ID`
ist in einem Beispiel möglich, aber keine technische Vorschrift.

Das Plugin hat keinen allgemeinen Enum-Validator für `Maßnahme` und `Schaltungsart`.
Die folgenden Werte stammen aus den mitgelieferten Darstellungsregeln:

| Feld | Tatsächlich ausgewertete Werte | Wirkung |
| --- | --- | --- |
| `Maßnahme` | Exakt `IBN` | Stil „Inbetriebnahme“ |
| `Maßnahme` | Exakt `ABN` | Stil „Außerbetriebnahme“ |
| `Maßnahme` | Anderer fachlich echter, nicht leerer Text | Kann zu „Gleichzeitig“ oder „Wechselweise“ gehören |
| `Maßnahme` | Leer / NULL | Die vorhandenen Leitungsregeln können keinen Treffer liefern: Import möglich, Schaltung möglicherweise unsichtbar |
| `Schaltungsart` | Exakt `Wechselseitig` oder `ww (wechselweise)` | Stil „Wechselweise“, wenn Maßnahme weder IBN noch ABN ist |
| `Schaltungsart` | Anderer Text oder NULL | Stil „Gleichzeitig“, wenn Maßnahme weder IBN noch ABN und nicht NULL ist |
| `Schaltung` | Exakt `Täglich` oder `t (täglich)` | Beschriftungsregel für tägliche Schaltung |
| `Schaltung` | Anderer Wert / leer | ELSE-Beschriftung für durchgehende Schaltung |

Nicht selbst anliefern: `MJAP-ID_Schaltung`, `MJAP-ID_x`, `MJAP-ID_y`,
`Element Typ`, `Station Anfang`, `Standort_von` und die internen Hilfsspalten.
Der Parser weist reservierte Zusatzspalten zurück. Die vollständige aktuelle
Liste steht im maschinenlesbaren `datenvertrag.json` unter `reserved_outage_columns`.
Weitere freie Zusatzspalten können übernommen werden, sind aber nicht pauschal
auf jeden Typ- oder Namenskonflikt geprüft.

## 8. Projekte.csv – Projektdaten als zusätzliche Quelle

Alle vier Spalten sind Pflichtüberschriften. Im abgesicherten Modus muss
mindestens ein echter Datensatz vorhanden sein.

<!-- TABLE:projects -->

Mehrere Standorte gehören in **eine** Zelle, z. B.
`Amprion_Berlin_380,Amprion_Hamburg_380`; wegen des inneren Kommas muss das
CSV-Feld in Anführungszeichen stehen. Der Parser entfernt Leerzeichen nach
den Listentrennern. Beim direkten Plugin-Import darf darauf nicht vertraut werden.
Eine zusätzliche Projekt-ID wird für den aktuellen Join nicht gebraucht;
der Join-Schlüssel ist `Projektname`. Keine frei erfundene Pflicht-ID ergänzen.

## 9. Beziehungen zwischen den Tabellen

<!-- FIG:beziehungen -->

| Verbindung | Schlüssel auf der linken Seite | Ziel | Kardinalität / Bedeutung |
| --- | --- | --- | --- |
| Netzelement → Anfangsstation | `Station Anfang:MJAP-ID` | `Stationen.MJAP-ID` | Ein Endpunkt; viele Elemente können denselben Standort referenzieren |
| Netzelement → Endstation | `Station Ende:MJAP-ID` | `Stationen.MJAP-ID` | Zweiter Endpunkt |
| Y-/T-Anschluss → Station | Belegtes T-/Y-Referenzfeld | `Stationen.MJAP-ID` | Bedingt nötig bei Y-/Doppel-Y-Topologie |
| Schaltung → Netzelement | `Netzelement:MJAP-ID` | `Netzelemente.MJAP-ID` | Ein Element je Schaltungsdatensatz; ein Element kann viele Schaltungen haben |
| Schaltung → Projekt | `Projekt` | `Projekte.Projektname` | Optionaler Projektbezug; ein Projekt kann viele Schaltungen haben |
| Projekt → Standorte | Kommagetrennte Liste `betroffener Standort` | `Stationen.MJAP-ID` | Ein oder mehrere Standorte pro Projekt; derselbe Standort kann zu mehreren Projekten gehören |
| Element → gezeichnete Linien | Nach Topologie erzeugte Legs | `SK.csv` / Stromkreise | Ein Element kann eine, drei oder fünf Teilstrecken besitzen |

**Ein Projekt allein erzeugt keine Projektleitung.** „Stromkreise Projekte“
verwendet die Schaltungsgeometrien und deren Projektbezug. Ein Projekt mit
betroffenen Standorten, aber ohne zugehörige Schaltung, kann daher bei den
Standortprojekten sichtbar sein, ohne eine Leitung im Projektlayer zu erzeugen.

## 10. MJAP-Eingang: Was ist wirklich Pflicht?

Der zuverlässigste Eingang ist das unveränderte, vierteilige Parser-Paket aus
`--mjap`. Wer CSVs direkt erstellt, muss zusätzlich verstehen, dass das Plugin
Spalten ohne zentrale Vorabprüfung direkt anspricht. Es kann Daten ausfiltern,
statt sofort einen Fehler zu zeigen.

| Datei | Direkt benötigte Überschriften im aktuellen Plugin-Pfad |
| --- | --- |
| `Stationen.csv` | `MJAP-ID`, `lat`, `long`, `IBN`, `ABN`, `Eigentümer`, `Spannung`, `Stationsname - Langname`, `reales UW`, `ID-OPC` |
| `Netzelemente.csv` | `MJAP-ID`, `Station Anfang:MJAP-ID`, `Station Ende:MJAP-ID`, `Station T-1:MJAP-ID`, `Station T-2:MJAP-ID`, `Y-Knoten-1: MJAP-ID`, `Y-Knoten-2: MJAP-ID`, `IBN`, `ABN`, `IBN - Mehrfach`, `ABN - Mehrfach`, `Eigentümer`, `Spannung`, `Stromkreisname - Langname`, `Element Typ`, `relevant für`, `ID-OPC`, `Region`, `Station Anfang` |
| `Freischaltungen.csv` | Konvertierung: `MJAP-ID`, `Netzelement:MJAP-ID`, `interne ID`, `von`, `bis`; Assistent zusätzlich `Projekt`; Stile zusätzlich `Maßnahme`, `Schaltungsart`, `Schaltung` |
| `Projekte.csv` | Konvertierung: `Umsetzungzeitraum von`, `Umsetzungzeitraum bis`; Assistent zusätzlich `Projektname`, `betroffener Standort` |

Auch ein optionaler Wert wie `ID-OPC` benötigt hier eine vorhandene Spalte.
Ein manueller Import ist nicht gleich sicher wie die Parser-Validierung.
Insbesondere müssen Mehrfachterminspalten trotz unbekannter Termine für `.str`
als Text lesbar bleiben. Der Parser erledigt dies; eine komplett leere manuelle
Mehrfachterminspalte kann den Import bereits abbrechen.

## 11. MJAP-Menüs: Eingabe, Aufgabe, Ausgabe

| Menü / Werkzeug | Erwartete Eingabe | Was geschieht | Was anschließend vorhanden ist |
| --- | --- | --- | --- |
| `Visualisierung erstellen` | Ordner mit den vier Eingabe-CSVs; vorhandener Ausgabeordner | Führt Konvertierung, Geometrieexport, Layerimport, Joins, Stile und Zeitkonfiguration aus | Die kompletten Visualisierungslayer in QGIS |
| `Werkzeuge → Sharepoint2QGIS` | Dieselben vier CSVs | Nur CSV-/Attributaufbereitung und Fehlerbericht | SO/SK-Zwischen-CSVs und zwei XLSX-Dateien; noch nicht der komplette Kartenschritt |
| Netzshapedateien-Werkzeug | SO/SK-Zwischentabellen bzw. entsprechend zugeordnete Spalten | SpatiaLite erstellt Punkte und Linien | Shapefiles; geometrische Attribute allein enthalten noch nicht alle Stammdaten |
| `Schaltungen importieren` | Bereits importierte, geometrielose Tabelle und vorhandene Stromkreis-/Standortlayer | Geometrien anhand eingestellter ID-/Referenzfelder zuweisen | Räumliche Schaltungs- oder Projektlayer |
| `Zeitreihenlayer erstellen` | Vorhandener Layer, echte Datumsfelder, Beobachtungszeitraum | Virtuelle SQL-Layer nach Zeitschritten erzeugen | Layer pro Jahr, Quartal, Monat, Woche oder Gesamtzeitraum |

Der Assistent erwartet CSVs im ausgewählten **Ordner**. Er nimmt dort nicht die
ursprüngliche Excel-Datei als unmittelbare Eingabe entgegen.

## 12. Zwischenprodukte des Plugins: nicht als Eingabe vorbereiten

### 12.1 SO.csv und SK.csv

Diese Dateien erzeugt Sharepoint2QGIS selbst. Hier gelten andere CSV-Regeln:
**Semikolon** als Spaltentrenner und **Punkt** als Dezimalzeichen. Sie sind nicht
mit `Stationen.csv` und `Netzelemente.csv` zu verwechseln.

<!-- TABLE:intermediate -->

`shape-ID` unterscheidet gezeichnete Legs, z. B. `SK_A_Y1`; `MJAP-ID` bleibt
der gemeinsame fachliche Elementschlüssel. Der Shapefile-Worker verwendet
`MJAP-ID` für die Linienkennzeichnung, deshalb können mehrere Geometrien
desselben Elements denselben Schlüssel haben.

### 12.2 attribute.xlsx – vier intern erzeugte Arbeitsblätter

| Blatt | Felder / Herkunft | Datentyp und Leerregel |
| --- | --- | --- |
| `SO_Attribute` | `MJAP-ID`, `IBN`, `ABN`, `Eigentümer`, `Spannung`, `Stationsname - Langname`, `reales UW`, `ID-OPC` | ID/Text plus Excel-Datumswerte; unbekanntes ABN bleibt leer |
| `SK_Attribute` | `shape-ID`, `MJAP-ID`, `IBN`, `ABN`, `Eigentümer`, `Spannung`, `Stromkreisname - Langname`, `Element Typ`, `relevant für`, `ID-OPC`, `Region` | Ein Attributsatz pro erzeugter Teilstrecke; IBN/ABN sind Datumswerte |
| `Schaltungen` | Ausgangsspalten plus `MJAP-ID_Schaltung`, `MJAP-ID_x`, `MJAP-ID_y`, `Element Typ`, `Standort_von` | `von`/`bis` als Datum; `Standort_von` nur bei `Trafo`, sonst leer |
| `Projekte` | Die übernommenen Projektspalten | Umsetzungszeitraum von/bis als Datum; sonst Text |

| Internes Schaltungsfeld | Bedeutung | Selbst befüllen? |
| --- | --- | --- |
| `MJAP-ID_Schaltung` | Kopie von `interne ID` | Nein |
| `MJAP-ID_x` | Aufgelöste Netzelement-ID, ggf. einer zeitlichen Variante | Nein |
| `MJAP-ID_y` | Ursprüngliche Schaltungs-MJAP-ID | Nein |
| `Element Typ` | Übernahme des Netzelementtyps | Nein |
| `Standort_von` | Anfangsstandort des Transformators; bei anderen Typen leer | Nein |
| `MJAP-ID_orig`, `MJAP-UID` | Interne Ursprungs-/Phasen-ID der Netzelementverarbeitung | Nein; keine externen Pflichtspalten |

### 12.3 missing_data.xlsx und Worker-Log

| Bericht / Datei | Aussage | Was prüfen? |
| --- | --- | --- |
| `Fehlende Standorte` | Stationsdatensätze ohne erzeugten Standortpunkt | Koordinaten und MJAP-ID |
| `Fehlende Stromkreis-Shapes` | Netzelemente ohne erzeugte Linie; `Trafo` ist in dieser Prüfung ausgenommen | Anschlüsse, alle Y-/T-Referenzen; Transformatoren zusätzlich direkt im Layer prüfen |
| `Fehlende Schaltungen` | Schaltungen ohne Treffer im Netzelement-Merge | `Netzelement:MJAP-ID` und vorhandene Netzelemente |
| `SK.log` | Geometrieworker: Datensatzzahlen, fehlende Anschlüsse, unreferenzierte Standorte, identische Endpunkte | Vor allem Fehlertexte; ein leerer XLSX-Fehlerbericht allein beweist nicht vollständige Geometrien |

Die Erfolgsmeldung „Konvertierung von Sharepoint Daten abgeschlossen“ bedeutet
zunächst, dass die Funktion beendet wurde. Sie ersetzt weder den Fehlerbericht
noch die Prüfung der tatsächlichen Layeranzahlen und Verknüpfungen.

## 13. QGIS-Layer, Schlüssel, Datumsfelder und Projektdatei

<!-- TABLE:layers -->

Die geometrischen Basislayer sind in EPSG:25832. Eingabekoordinaten werden aus
EPSG:4326 transformiert. Dargestellte Leitungen sind schematische Verbindungen
zwischen Standorten mit Versatz bei parallelen Verbindungen, keine nachgewiesenen
realen Leitungstrassen.

Die Dateien `Schaltungen_SK.gpkg`, `Schaltungen_SO.gpkg` und `Projekte_SO.gpkg`
werden vom Assistenten geschrieben. „Stromkreise Projekte“ nutzt ebenfalls
`Schaltungen_SK.gpkg` und erhält einen Projektjoin; dafür entsteht im aktuellen
Code kein eigener vierter Projektlinien-GeoPackage-Export.
`Netzregionen.gpkg` wird aus den Plugin-Ressourcen in den Ausgabeordner kopiert.

Der Assistent speichert die QGIS-Projektdatei nicht selbst. Nach dem Import in
QGIS **Projekt speichern unter** verwenden. Eine `.qgz` enthält normalerweise
Verweise auf Shapefiles, GeoPackages und Attributdateien, keine garantierte Kopie
aller Datendateien. Den Ausgabeordner zusammen mit dem Projekt aufbewahren.
Bei Shapefiles gehören `.shp`, `.shx`, `.dbf`, `.prj` und ggf. weitere Begleitdateien
zusammen; nicht nur die `.shp` verschieben.

### 13.1 Erwartete Plugin-Einstellungen

| Einstellung | Standard | Bedeutung |
| --- | --- | --- |
| `standorte_id` | `id` | ID-Feld des Standort-Shapefiles |
| `stromkreise_id` | `schlüssel` | Element-ID des Stromkreis-Shapefiles |
| `schaltungen_ref` | `MJAP-ID_x` | Netzelementreferenz in der intern erzeugten Schaltungstabelle |
| `schaltungen_so_ref` | `Standort_von` | Standortreferenz für Transformator-Schaltungen |

Diese Namen gehören zu unterschiedlichen Verarbeitungsstufen. `id` und
`schlüssel` sind keine neu benötigten Spalten der ursprünglichen Excel-Datei.
Die geprüften Abläufe benutzen die Standardeinstellungen. Abweichende
Feldzuordnungen können funktionierende CSVs nachträglich unbrauchbar machen.

### 13.2 Sichtbarkeit und zeitliche Darstellung

Die Standortstile erkennen insbesondere Spannungen `220` und `380` sowie
`reales UW` in der vom Plugin umgewandelten Form `true`/`false`.
Andere Spannungsklassen können mit den vorhandenen Regeln unsichtbar bleiben.
Die Stromkreisfarben werden über `Attribute_Spannung` kategorisiert; die
vorhandenen Kategorien sind `220`, `380`, `DC` und eine Standardkategorie.
Projektfarben werden anhand `Projektname` erzeugt und auf Projektleitungen übertragen.

Die zeitlichen Layer-Eigenschaften des Assistenten und das separate
Zeitreihenwerkzeug sind zwei verschiedene Funktionen. Das Zeitreihenwerkzeug
benutzt aktuell die Bedingung:

```sql
IBN <= Ende_des_Zeitschritts AND ABN >= Anfang_des_Zeitschritts
```

Bei NULL/leerem ABN liefert der zweite Vergleich keinen Treffer. Datensätze ohne
bekanntes ABN können daher **aus den virtuellen Zeitreihenlayern verschwinden**,
obwohl sie importiert wurden. Das ist eine Einschränkung dieses Werkzeugs,
keine Aufforderung, ein Enddatum zu erfinden. Die Oberfläche verlangt echte
Datumsspalten und einen Beobachtungsbeginn vor dem Beobachtungsende.

## 14. Schritt für Schritt: geprüfter vollständiger Import

1. Excel-Netzblatt mit den 13 Pflichtüberschriften und echten Werten vorbereiten.
   SUB-Zeilen brauchen Koordinaten; Netzelementzeilen brauchen zwei gültige
   Stationsreferenzen. Im abgesicherten Weg hat jede Zeile eine gültige IBN.
2. Echte, nicht leere `Freischaltungen.csv` und `Projekte.csv` vorbereiten.
   In deren Referenzen bereits die vom Parser erzeugten IDs `TSO_ELEMENT ID`
   verwenden, nicht die Excel-Roh-IDs. Ohne solche Quellen ist der vollständige
   Assistentenweg derzeit nicht verfügbar.
3. Im Parser-Verzeichnis den MJAP-Modus ausführen. Einen eigenen Exportordner
   für das vierteilige Paket verwenden:

```bash
.venv/bin/python converter.py input.xlsx --mjap \
  --freischaltungen Freischaltungen.csv \
  --projekte Projekte.csv \
  --issue-file output/pruefung.csv \
  --debug-file output/konvertierung.log \
  -o output/mjap
```

4. Exit-Code und Protokoll prüfen. `0` bedeutet erfolgreicher Parserlauf,
   `2` bedeutet Konvertierungs-/Validierungsfehler, `1` unerwarteter Fehler
   oder Abbruch. Warnungen, insbesondere Koordinatenreparaturen, nachprüfen.
   Alle vier CSVs müssen aus demselben beendeten Lauf stammen.
5. QGIS 3 mit kompatibler MJAP-Umgebung öffnen. Für einen neuen Prüflauf ein
   leeres QGIS-Projekt und einen neuen, vorhandenen Ausgabeordner verwenden.
6. Im MJAP-Menü **Visualisierung erstellen** auswählen. Eingabeordner:
   `output/mjap`; Ausgabeordner: ein separater Ordner, etwa `output/qgis-lauf-01`.
7. `missing_data.xlsx`, `SK.log`, Layeranzahlen und Attributjoins kontrollieren.
   Sichtbarkeit, Spannungsstile, Schaltungsstilwerte und zeitliche Filter prüfen.
8. QGIS-Projekt speichern und den kompletten Datenausgabeordner aufbewahren.
9. Falls gewünscht, die Länderkarte anschließend ergänzen und das neue Projekt öffnen.

Der Paketexport schreibt zunächst alle vier CSVs in einen temporären Unterordner.
Bei normalen Schreib-/Dateiaustauschfehlern wird das vorherige Paket wiederhergestellt.
Dies ist keine Transaktion bei abruptem Prozessende oder für gleichzeitig lesende
Programme. Den Import erst nach abgeschlossenem Export starten; fehlgeschlagene
Läufe können noch einen älteren, bereits vorhandenen Exportordner hinterlassen.

## 15. Durchgehendes Dummy-Beispiel

Alle Werte dieses Abschnitts und die vier CSVs in `beispiel/mjap/` sind **Dummy-Daten**.
Die Ortsnamen bezeichnen ein Rechenbeispiel, kein dokumentiertes reales Netz.

Das ausgewählte Excel-Blatt enthält folgende Kernwerte; die 13 Pflichtspalten
müssen insgesamt vorhanden sein. `DESCRIPTION`, `UCTE CODE` und die übrigen
in dieser Übersicht nicht gezeigten Pflichtüberschriften können entsprechend
der Feldtabelle ergänzt bzw. leer geführt werden.

| TSO | ELEMENT ID | ELEMENT-TYPE | Station 1 | Station 2 | Latitude | Longitude | VOLTAGE-LEVEL | STARTLIFETIME |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Amprion | Berlin_380 | SUB | leer | leer | 52.459373 | 13.361402 | 380 | 2025-05-09 |
| Amprion | Hamburg_380 | SUB | leer | leer | 53.55 | 9.99 | 380 | 2025-05-09 |
| Amprion | LINE_471 | LINE | Berlin_380 | Hamburg_380 | leer | leer | 380 | 2025-05-09 |
| Amprion | TRA_1 | TRA | Berlin_380 | Hamburg_380 | leer | leer | 380 | 2025-05-09 |

Hieraus erzeugt der Parser beispielsweise die Stations-ID
`Amprion_Berlin_380` und die Transformator-ID `Amprion_TRA_1`.
Die externe Schaltungsquelle referenziert `Amprion_TRA_1`, nicht bloß `TRA_1`:

```csv
MJAP-ID,Netzelement:MJAP-ID,interne ID,von,bis,Projekt,Maßnahme,Schaltungsart,Schaltung
FS_1,Amprion_TRA_1,FS_1,01.06.2028,02.06.2028,Demo,IBN,gleichzeitig,Täglich
```

Die externe Projektquelle verbindet zwei Stationen in einer zitierten Zelle:

```csv
Projektname,betroffener Standort,Umsetzungzeitraum von,Umsetzungzeitraum bis
Demo,"Amprion_Berlin_380,Amprion_Hamburg_380",01.01.2028,31.12.2028
```

Das zugehörige befüllte Viererpaket wurde mit dem vollständigen Assistenten
geprüft. Erwartet werden zwei Standorte, zwei Stromkreise, eine Transformator-
Standortschaltung, eine Stromkreisschaltung, ein Standortprojekt als MultiPoint
mit zwei enthaltenen Punkten und eine Projektleitung. Ein MultiPoint mit zwei
Punkten ist **ein** Projekt-Feature, nicht zwei Tabellenzeilen.
Die unbekannten ABN werden nicht durch Dummy-Enddaten ersetzt.

Die vollständige Excel-Datei, beide zusätzlichen Quellen und das daraus geprüfte
Viererpaket liegen in [beispiel/README_DE.md](beispiel/README_DE.md).

## 16. Länderkarte: Niederlande, Belgien und Frankreich

Die mitgelieferten Offline-Grenzen umfassen DE/NL/BE/FR. Sie sind zusätzliche
Hintergrundlayer und erzeugen keine Stationen, Leitungen oder Projekte in diesen
Ländern. Dazu wären weiterhin echte Netzdaten nötig.

Nach dem MJAP-Assistenten das QGIS-Projekt speichern. Aus dem Parser-Verzeichnis:

```bash
bash scripts/country_map.sh \
  --project output/qgis-lauf-01/Mein-Netz.qgz \
  --output output/karte/Mein-Netz-Laender.qgz \
  --countries DE NL BE FR
```

Das Werkzeug erzeugt eine Projektkopie und `Laender.gpkg`; bestehende Layer
bleiben erhalten. Eine Vorschau ist mit `--preview output/karte/Uebersicht.png`
möglich. `--osm` ergänzt auf Wunsch eine Online-Straßenkarte mit Attribution;
diese benötigt Internet. Die Kartenquelle und Lizenz sind in
`excelToCsv/maps/SOURCE.md` im Parser dokumentiert.

Der MJAP-Assistent blendet Layer ohne passenden eigenen Stil aus. Länder deshalb
nach dem Assistenten hinzufügen; nach einem erneuten Assistentenlauf die
Ländergruppe wieder aktivieren oder das Kartenwerkzeug erneut anwenden.

## 17. Fehlerbilder und Abhilfe

| Symptom | Ursache / Einordnung | Abhilfe |
| --- | --- | --- |
| Parser meldet fehlende Eingabespalte | Eine der 13 Überschriften fehlt, auch wenn ihre Werte optional wären | Überschrift gemäß Excel-Katalog ergänzen; richtiges Blatt auswählen |
| `Dateien nicht gefunden` | Plugin findet nicht alle vier exakt benannten CSVs im ausgewählten Ordner | Den kompletten Paketordner auswählen; Dateinamen kontrollieren |
| `KeyError: MJAP-ID` in `sk_df` | Keine Leitungsgeometrie erzeugt: z. B. Leerzeichen in T-/Y-Referenzen aus dem alten Standardformat oder ungültige Stationsreferenzen | CSVs mit dem aktuellen einfachen Excel-Aufruf neu erzeugen; die Netztabellen im MJAP-Eingabeordner ersetzen; den alten `--legacy`-Export nicht verwenden |
| `KeyError` auf eine andere CSV-Spalte | Header fehlt, ist umbenannt oder hat andere Leerzeichen | Kanonische Überschrift wiederherstellen; aktuellen MJAP-Netzexport verwenden |
| `KeyError: Standort_von` bei leeren Schaltungen | XLSX-Treiber erkennt Kopfzeile ohne Daten nicht als erwartete Felder | Nicht leere echte Begleittabellen verwenden; nicht mit Dummy-Datensätzen kaschieren |
| Layerfelder heißen `Field1`, `Field2`, … | XLSX-Kopfzeile wurde als Daten gelesen, z. B. bei vollständig leeren Betriebsdaten | Im geprüften Parserweg gültige IBN-Daten führen; keine erfundenen Termine |
| `.str`-Fehler | Vollständig leere Mehrfachterminspalte wurde numerisch eingelesen | Den vom MJAP-Parser erzeugten Text-/Leerwertvertrag verwenden |
| `columns must have matching element counts` | IBN-/ABN-Listen haben unterschiedliche Länge | Direkte Plugin-Mehrfachtermine paarweise führen; im Parserweg einzelne Termine verwenden |
| Station oder Leitung fehlt | Ungültige Koordinaten oder Referenzen; Teilstrecken wurden ausgefiltert | Fehlerblätter, IDs und alle belegten Y-/T-Referenzen kontrollieren |
| Transformator-Schaltung hat keinen Standort | Elementtyp nicht exakt `Trafo` oder `Station Anfang` keine vollständige Stations-ID | Kanonische Typübersetzung und Stationsreferenz verwenden |
| Erfolgreicher Import, aber Schaltung unsichtbar | Leere `Maßnahme`, unbekannte Stilklasse, Layer ausgeblendet oder Zeitfilter aktiv | Fachliche Stilwerte, Sichtbarkeit und Zeitfilter prüfen |
| Standort mit anderer Spannung unsichtbar | Standortregeln konzentrieren sich auf 220/380 | Passenden eigenen QGIS-Stil für die vorhandene Spannung auswählen |
| Virtuelle Zeitreihe lässt Datensätze aus | NULL-ABN erfüllt den aktuellen SQL-Vergleich nicht | Einschränkung berücksichtigen; Daten nicht mit erfundenen Endterminen verändern |
| pandas-Warnung „Could not infer format“ | Vollständig unbekanntes ABN im unveränderten Plugin | In getesteten Fällen harmlose Warnung; keine Garantie bei anderen Bibliotheksversionen |
| Geometrie-/Workerfehler | Gleiche Endkoordinaten, ungeeignete IDs, fehlendes SpatiaLite oder geänderte Umgebung | Parser-Validierung beachten; dokumentierte QGIS-Umgebung verwenden; `SK.log` prüfen |

## 18. Nachweise, Grenzen und Wiederholung der Prüfungen

Die Basisprüfung ergab 400 bestandene Parser-Tests und 35 bestandene Tests in
der echten QGIS-Umgebung, darunter drei vollständige Visualisierungsassistenten-
läufe. Geprüft wurden Geometrien, Mengen, Joins, Zeitfelder und aktive
Regelausdrücke. Details stehen im Parser in `MJAP_PRUEFBERICHT_DE.md`.

Die Dreibein-Erweiterung wurde zusätzlich mit 410 Parser-Tests (pandas 3.0.5)
und 59 Tests in der echten QGIS-/MJAP-Umgebung (pandas 2.2.3), einschließlich
eines vollständigen Dreibein-Assistentenlaufs, geprüft. Die
[Dreibein-Prüfdateien](beispiel/dreibein/README_DE.md) enthalten das tatsächliche
Ergebnis. Vier Stationen und fünf gültige Linienobjekte; die vollständige
Y-Schaltung und das zugehörige Projekt enthalten jeweils alle drei Y-Beine.
Der Test prüft auch Quell-IDs, Namen, Stationspaare und leere T-/Y-Felder der
Paarzeilen. Keine GUI-Warnung, keine kritische Meldung und keine Fehler in den
geprüften aktiven Regelausdrücken; die bekannte ABN-Datumswarnung bleibt möglich.

Die anschließende Korrektur des CLI-Standardexports reproduziert den gemeldeten
`KeyError: MJAP-ID` mit dem alten Leerzeichenformat im echten MJAP-Code. Der
einfache neue Excel-Aufruf erzeugt dagegen bei normalen Leitungen zwei und
beim Dreibein fünf nutzbare Shape-/Attributzeilen. Seine Netztabellen sind
bytegenau identisch mit denen des geprüften Viererpakets. Der frühere Hinweis,
den Standardexport direkt in MJAP zu importieren, war falsch; dafür wird nun
der korrigierte Standardexport verwendet. Nachgewiesen sind 422 Parser-Tests
und 74 Tests in der echten QGIS-/MJAP-Umgebung. Das Plugin wurde nicht geändert.
Die konkreten fehlerhaften Windows-Dateien wurden nicht bereitgestellt; ungültige
Stationsreferenzen können denselben KeyError verursachen und werden im neuen
Export vor dem Schreiben abgewiesen.

Der unterstützte Teststand ist QGIS 3.40.3 / Qt 5 / Python 3.12 / pandas 2.2.3
für MJAP. Die Parser-Tests laufen zusätzlich mit pandas 3.0.5. Daraus folgt
keine Freigabe des Plugins für pandas 3 oder QGIS 4 / Qt 6.
Die Umgebung ist in `mjap_plugin/environment.yml` beschrieben; die konkreten
installierten Builds stehen in `environment-osx-arm64.lock.txt`.

Im Parser-Verzeichnis:

```bash
.venv/bin/python -m pytest
bash scripts/test_mjap.sh
```

Im MJAP-Verzeichnis:

```bash
bash scripts/local.sh test
bash scripts/local.sh gui
```

Nicht zugesichert sind beliebige Fremd-CSV-Zusatzspalten, sämtliche numerischen
ID-Inferenzfälle, fachlich richtige Schaltungs-/Projektzeiträume, ein automatischer
Export aller Excel-Blätter, automatische Vierbein-/Mehrfachstromkreis-Gruppen oder die virtuelle
Zeitreihendarstellung bei NULL-ABN. Die Eingabe kann technisch gültig und fachlich
trotzdem falsch sein. Dummy-Tests ersetzen keine Abnahme mit echten Netzdaten.

Leere Begleittabellen werden jetzt vor dem Export abgewiesen. Die Treiberoption
`OGR_XLSX_HEADERS=FORCE` hatte die Ein-Kopfzeilen-Fälle in der installierten
Umgebung nicht zuverlässig behoben. Das ist ein beobachteter Befund; keine
allgemeine Aussage über sämtliche GDAL-Versionen.

## 19. Codequellen des Datenvertrags

| Thema | Maßgebliche Datei |
| --- | --- |
| Excel- und Ausgabeüberschriften | Parser: `excelToCsv/schema.py` |
| Blatt-/Kopfzeilenauswahl | Parser: `excelToCsv/reader.py` |
| Typnormalisierung, Datums-/Koordinatenwerte, IDs | Parser: `excelToCsv/normalize.py` |
| Stationen und leere/abgeleitete Felder | Parser: `excelToCsv/stations.py` |
| Netzelemente, Stations-/Multipod-Verweise | Parser: `excelToCsv/networkElements.py` |
| Relevanzspalten | Parser: `excelToCsv/relevance.py` |
| Allgemeine Prüfungen und Reihenfolge | Parser: `excelToCsv/validate.py`, `excelToCsv/pipeline.py` |
| MJAP-spezifische Regeln und Viererpaket | Parser: `excelToCsv/mjap.py` |
| CSV-/XLSX-Konvertierung und Phasen | MJAP: `toolbelt/sharepoint2qgis_v4.py` |
| Assistent, Layerjoins und Zeitfelder | MJAP: `plugin_main.py` |
| Geometrieexport und Worker-Log | MJAP: `toolbelt/tpzwplugin.py`, `gui/dlg_tpzwplugin.py` |
| Schaltungs-/Projektgeometrien | MJAP: `gui/dlg_schaltungen.py` |
| Virtuelle Zeitreihen und NULL-ABN-Bedingung | MJAP: `gui/dlg_zeitreihen.py` |
| Standardfeldzuordnungen | MJAP: `toolbelt/preferences.py` |
| Tatsächliche Darstellungswerte | MJAP: `resources/styles/*.qml` |
| Vollständige Verbraucherprüfungen | Parser: `tests/testMjapQgis.py`, `tests/testMjapWizard.py`, `tests/mjapWizardProbe.py` |

Die Feldkataloge liegen zusätzlich als [datenvertrag.json](datenvertrag.json) vor. Die vier
Diagramme liegen als SVG und als bearbeitbare Mermaid-Quellen in `abbildungen/`.
Die HTML-Leseversion enthält alle Diagramme direkt und benötigt kein Internet.
Die Dokumentation kann mit `python3 scripts/build_handbook.py` aus der Vorlage
und dem Feldkatalog neu erzeugt werden. Der Generator prüft die 13 Excel-
Pflichtüberschriften, die 20/30 CSV-Spalten sowie die Schaltungs-/Projektspalten
gegen den Parser-Quellcode; Abweichungen führen zum Abbruch der Dokumenterzeugung.
