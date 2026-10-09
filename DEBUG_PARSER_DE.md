# Parser mit Konstanten in VS Code debuggen

Projektordner: `/Users/hadi/Desktop/nahriva_works/parser`.
Privates Repository: https://github.com/hadiibrahim-Engin/parser.
Die Arbeitsänderungen liegen auf `main`. Die vorhandene Parser-Historie wurde
übernommen; ein Migrationstag erhält die frühere, nicht in main enthaltene
experimentelle GUI-Branch. Die Konvertierung verwendet weiterhin dieselbe
Parser-Pipeline; das MJAP-Plugin wird dabei nicht gestartet.

1. Den **neuen Projektordner** in VS Code öffnen.
2. Über **Python: Select Interpreter** die Projektumgebung auswählen:
   `.venv/bin/python` auf Mac/Linux; `.venv\Scripts\python.exe` auf Windows.
3. `debug_parser.py` öffnen und oben mindestens `INPUT_XLSX` und `OUTPUT_DIR` ändern.
4. Im Menü neben dem Ausführen-Pfeil **Python Debugger: Debug Python File** wählen.
   Dafür ist keine `launch.json` nötig. **F5 → Python Debugger → Python File**
   funktioniert ebenfalls, sofern keine andere Debug-Konfiguration ausgewählt ist.
5. Mit `PAUSE_AT_START = True` hält der angeschlossene Debugger vor der
   Konvertierung automatisch an. Mit **F11** in `runConversion()` hineingehen,
   mit **F10** zeilenweise weitergehen und mit **Shift+F11** eine Funktion verlassen.
6. Einen Breakpoint nach `result = runConversion(...)` setzen. Dort enthalten
   `result.stations`, `result.networkElements`, `result.issues` und
   `result.excludedRows` die Ergebnisdaten.

Windows-Pfade als rohe Zeichenfolge angeben:

```python
INPUT_XLSX = Path(r"C:\Daten\netz.xlsx")
OUTPUT_DIR = Path(r"C:\Daten\output-debug")
```

Die Standardeinstellung nutzt das gekennzeichnete Excel-Dummy-Beispiel und
schreibt nach `output/debug-parser`. Erwartet: sechs Stationen, zwei Netzelemente
und sieben ausgeschlossene Excel-Zeilen. Es entstehen zusätzlich
`Fehlerliste.csv`, `Pflegebericht.html` und `parser-debug.log`.

`DEBUG_LOG` ist eine eigene Konstante: Wenn du `OUTPUT_DIR` während eines
laufenden Debugger-Halts änderst, musst du den Logpfad ebenfalls ändern.
Bei Änderungen oben in der Datei vor einem Neustart wird der Logpfad automatisch
aus dem neuen Ausgabeordner aufgebaut.

Der Debug-Einstieg fängt Konvertierungsfehler nicht ab. **Raised Exceptions**
aktivieren, wenn VS Code am ursprünglichen Fehler anhalten soll. Normale
Breakpoints funktionieren auch ohne Fehler. Der direkte Debug-Lauf endet bei
erfolgreichem Teil-Export normal; die CLI verwendet dafür weiterhin Exit-Code 3.

Ohne Debugger ausführen:

```bash
.venv/bin/python debug_parser.py
```

Einrichtung einer frischen Umgebung:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,fast]'
```

Quellen: [VS Code: Python-Datei direkt debuggen](https://code.visualstudio.com/docs/python/debugging#_basic-debugging),
[VS Code: Schritte und Breakpoints](https://code.visualstudio.com/docs/debugtest/debugging).
