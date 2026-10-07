# Dummy-Beispiel: geprüfter Teil-Export

Alle Daten sind fiktiv. `DUMMY_TeilExport.xlsx` ist die Eingabe; `output/` enthält
die beiden MJAP-Netztabellen sowie automatisch erzeugte Fehlerliste und Pflegebericht.
`PRUEFERGEBNIS.json` nennt den geprüften Bestand und die ausgeschlossenen Excel-Zeilen.

Aus dem Parser-Verzeichnis erneut erzeugen:

```bash
.venv/bin/python converter.py docs/beispiel/teil-export/DUMMY_TeilExport.xlsx \
  -o docs/beispiel/teil-export/output --details
```

Erwarteter CLI-Status: **3**, weil ein geprüfter Teil-Export veröffentlicht wird.
Die Warnung zur Station `Pflege` sperrt auch deren Leitung. Fehlende IBN und
fehlende Anschlüsse sperren die jeweiligen Elemente. Ein defektes Datum an einem
Dreibein-Bein sperrt alle drei Beine. Die unabhängige Leitung und der Transformator
bleiben erhalten. Die übrigen gültigen Stationen bleiben ebenfalls erhalten.

Pflegebericht offline öffnen: [Pflegebericht.html](output/Pflegebericht.html).
Die Excel-Datei wird beim Export nicht verändert.
