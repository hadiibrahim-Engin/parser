"""Automatic, Excel-traceable maintenance artifacts for each export attempt."""
from __future__ import annotations

import csv
import re
from collections import Counter
from datetime import datetime
from html import escape
from pathlib import Path

from openpyxl.utils import get_column_letter

from excelToCsv.issues import Issue, formatValue, sortIssues

CSV_COLUMNS = ('Schweregrad', 'Quelldatei', 'Blatt', 'Quellzeile', 'Fundstelle', 'ELEMENT ID',
               'ELEMENT-TYPE', 'Feld', 'Wert', 'Problem', 'Erwartet', 'Pflegehinweis')


def sourceLocation(issue: Issue, sheet: str, columnLetters: dict[str, str]) -> str:
    """Render the physical input location without substituting an output row.

    Match a complete heading before splitting composite fields, since relevance
    headings themselves may contain slashes or commas.
    """
    if issue.row is None:
        return 'Tabellenstruktur / Exportkonfiguration (keine einzelne Quellzeile)'
    if issue.source:
        return f'CSV-Zeile {issue.row}'
    fields = ([issue.field] if issue.field in columnLetters
              else re.split(r',\s*| / ', issue.field))
    cells = [f'{columnLetters[field]}{issue.row}' for field in fields if field in columnLetters]
    prefix = f'Excel-Zeile {issue.row}'
    if not sheet:
        return prefix
    quotedSheet = "'" + sheet.replace("'", "''") + "'"
    if not cells:
        return f'{prefix}, Blatt {quotedSheet}'
    return f'{prefix}: ' + ', '.join(f'{quotedSheet}!{cell}' for cell in cells)


def writeMaintenanceReports(inputPath, outputDir, table, result, issues, *, published):
    """Reports are separate from MJAP input tables; never modify source Excel."""
    outputDir = Path(outputDir)
    outputDir.mkdir(parents=True, exist_ok=True)
    ordered = sortIssues(issues)
    sheet = table.sheetName if table is not None else ''
    columnLetters = ({str(column): get_column_letter(position + 1)
                      for position, column in enumerate(table.frame.columns)}
                     if table is not None else {})
    csvPath = outputDir / 'Fehlerliste.csv'
    with csvPath.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for severity, issue in ordered:
            writer.writerow((severity, issue.source or str(Path(inputPath).resolve()), '' if issue.source else sheet,
                             issue.row if issue.row is not None else '',
                             sourceLocation(issue, sheet, columnLetters), issue.elementId,
                             issue.elementType, issue.field,
                             formatValue(issue.value) if issue.field else '', issue.problem,
                             issue.expected, issue.action or 'Excel-Eingabe korrigieren und erneut exportieren.'))

    e = lambda value: escape(str(value), quote=True)
    counts = Counter(severity for severity, _ in ordered)
    excluded = set(result.excludedRows) if result is not None else set()
    status = 'Export veröffentlicht' if published else 'Export abgebrochen – keine neuen MJAP-CSV-Dateien veröffentlicht'
    summary = [f'<p><strong>{e(status)}</strong></p>',
               f'<p>Eingabe: {e(Path(inputPath).resolve())}<br>Blatt: {e(sheet)}<br>'
               f'Erzeugt: {e(datetime.now().astimezone().isoformat(timespec="seconds"))}</p>',
               f'<p>{counts["ERROR"]} Fehler; {counts["WARNING"]} Warnungen; '
               f'{len(excluded)} ausgeschlossene Excel-Zeilen.</p>']
    if result is not None and result.excludedCompanionCount:
        summary.append(f'<p>{result.excludedCompanionCount} ausgeschlossene Begleitdatensätze.</p>')
    if published:
        summary.append(f'<p>Geschrieben: {len(result.stations)} Stationen und {len(result.networkElements)} Netzelemente.</p>')
    else:
        summary.append('<p>Eventuell vorhandene ältere CSV-Dateien sind kein Ergebnis dieses Laufs. Vor einem QGIS-Import den Exportstatus prüfen.</p>')
    summary.append('<p>Pflege erfolgt in der ursprünglichen Excel-Datei. Fehler und Warnungen korrigieren, '
                   'abhängige Stationen/Dreibeine gemeinsam prüfen und danach denselben Exportbefehl erneut ausführen. '
                   'Ein Teil-Export ersetzt die CSV-Tabellen vollständig durch den verbleibenden geprüften Bestand; '
                   'ausgeschlossene Elemente fehlen entsprechend in der Karte.</p>')
    rows = ''.join('<tr>' + ''.join(f'<td>{e(value)}</td>' for value in (
        severity, issue.source or str(Path(inputPath).resolve()), '' if issue.source else sheet,
        issue.row if issue.row is not None else '', sourceLocation(issue, sheet, columnLetters),
        issue.elementId, issue.elementType, issue.field,
        formatValue(issue.value) if issue.field else '', issue.problem, issue.expected, issue.action,
    )) + '</tr>' for severity, issue in ordered)
    headers = ('Schweregrad', 'Quelldatei', 'Blatt', 'Quellzeile', 'Fundstelle',
               'ELEMENT ID', 'Typ', 'Feld', 'Wert', 'Problem', 'Erwartet', 'Pflegehinweis')
    tableHtml = '<table><thead><tr>' + ''.join(f'<th>{e(col)}</th>' for col in headers) + '</tr></thead><tbody>' + rows + '</tbody></table>'
    originals = []
    if table is not None:
        # Include normalized raw input values, not corrected output values.
        # Sheet/row references point to the unchanged original workbook.
        affected = excluded | {issue.row for _, issue in ordered if issue.row is not None and not issue.source}
        for position, number in enumerate(table.rowNumbers):
            if int(number) not in affected:
                continue
            cells = ''.join(f'<tr><th>{e(column)}</th><td>{e(formatValue(value))}</td></tr>'
                            for column, value in table.frame.iloc[position].items())
            originals.append(f'<details><summary>Excel-Zeile {int(number)} – '
                             f'{e(formatValue(table.frame.iloc[position].get("ELEMENT ID")))}</summary>'
                             f'<table>{cells}</table></details>')
    html = ('<!doctype html><html lang="de"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Pflegebericht – Excel zu MJAP</title><style>'
            'body{font-family:Arial,sans-serif;margin:2rem;color:#162536;line-height:1.5}'
            'table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{border:1px solid #ccd5df;padding:.5rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}'
            'th{background:#edf2f7}details{margin:1rem 0}summary{cursor:pointer;font-weight:bold}'
            '</style><body><h1>Pflegebericht: Excel → MJAP</h1>' + ''.join(summary)
            + '<h2>Befunde</h2>' + (tableHtml if ordered else '<p>Keine Befunde.</p>')
            + '<h2>Eingabewerte der betroffenen Elemente</h2>' + ''.join(originals) + '</body></html>')
    htmlPath = outputDir / 'Pflegebericht.html'
    htmlPath.write_text(html, encoding='utf-8')
    return csvPath, htmlPath
