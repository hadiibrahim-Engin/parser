"""Excel -> CSV im VS-Code-Debugger; alle Einstellungen stehen hier oben.

Datei öffnen -> Python Debugger: Debug Python File. Keine launch.json nötig.
Python-Interpreter des Projekts auswählen: .venv/bin/python (Mac/Linux) oder
.venv\\Scripts\\python.exe (Windows). Diese Datei startet ausschließlich den Parser.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ====================== HIER DEINE WERTE ÄNDERN ==============================
# Windows-Beispiel: Path(r"C:\Daten\mein_netz.xlsx")
INPUT_XLSX = ROOT / "docs/beispiel/DUMMY_Netz.xlsx"
OUTPUT_DIR = ROOT / "output/debug-parser"

SHEET = None                 # None: erstes Blatt; sonst Blattname oder Index (0-basiert)
HEADER_ROW = None            # None: automatisch; sonst Excel-Headerzeile (1-basiert)
ENGINE = "auto"              # "auto", "openpyxl" oder "calamine"
SHOW_DETAILS = True
LOG_LEVEL = "INFO"          # "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
DEBUG_LOG = OUTPUT_DIR / "parser-debug.log" # None: keine zusätzliche Logdatei
PAUSE_AT_START = True       # Im Debugger vor dem Parser-Aufruf automatisch anhalten
# ============================================================================


def run_debug():
    """Breakpoint hier setzen; result/Tabellen bleiben im Debugger sichtbar.

    Anders als die CLI fängt dieser Einstieg Konvertierungsfehler nicht ab:
    VS Code kann direkt beim ursprünglichen Fehler und dessen Variablen anhalten.
    """
    from excelToCsv.loggingSetup import addDebugFileHandler, configureLogging
    from excelToCsv.pipeline import runConversion

    if LOG_LEVEL not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("Unbekannter LOG_LEVEL.")

    # Ohne angeschlossenen Debugger startet kein interaktives pdb und kein Warten.
    debugpy = sys.modules.get("debugpy")
    debugger_connected = sys.gettrace() is not None or (
        debugpy is not None and debugpy.is_client_connected()
    )
    if PAUSE_AT_START and debugger_connected:
        breakpoint()

    logger = configureLogging(level=getattr(logging, LOG_LEVEL), color=False,
                              showDetails=SHOW_DETAILS)
    if DEBUG_LOG is not None:
        addDebugFileHandler(logger, Path(DEBUG_LOG))

    input_path = Path(INPUT_XLSX).expanduser().resolve()
    output_dir = Path(OUTPUT_DIR).expanduser().resolve()
    logger.info("Debug-Eingabe: %s", input_path)
    logger.info("Debug-Ausgabe: %s", output_dir)

    # F11 auf dieser Zeile führt in die echte Parser-Pipeline.
    result = runConversion(
        input_path,
        output_dir,
        logger,
        sheet=SHEET,
        headerRow=HEADER_ROW,
        engine=ENGINE,
    )
    # Breakpoint hier: result.stations, result.networkElements und result.issues untersuchen.
    logger.info("Debug-Lauf beendet: %d Stationen, %d Netzelemente.",
                len(result.stations), len(result.networkElements))
    return result


if __name__ == "__main__":
    result = run_debug()
