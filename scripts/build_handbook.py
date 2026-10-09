"""Build the German data handbook using only Python's standard library.

Run from either repository. This checks the field inventory against the parser
source, builds static SVG/Mermaid diagrams and a standalone HTML reading copy.
It does not change application code or import QGIS.
"""
from __future__ import annotations

import ast
import html
import json
import math
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
PARSER = ROOT if (ROOT / 'excelToCsv/schema.py').exists() else ROOT.parent / 'parser'


def source_constants(path):
    result = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name, value = node.targets[0].id, node.value
        else:
            continue
        try:
            result[name] = ast.literal_eval(value)
        except (ValueError, TypeError):
            if isinstance(value, ast.Tuple) and all(isinstance(item, ast.Name) and item.id in result for item in value.elts):
                result[name] = tuple(result[item.id] for item in value.elts)
    return result


def validate_inventory(data):
    schema = source_constants(PARSER / 'excelToCsv/schema.py')
    for section, column, constant in [('excel', 0, 'REQUIRED_INPUT_COLUMNS'),
                                      ('stations', 1, 'STATION_COLUMNS'),
                                      ('elements', 1, 'NETWORK_ELEMENT_COLUMNS')]:
        actual = tuple(row[column] for row in data[section]['rows'])
        assert actual == schema[constant], f'Documentation schema drift: {section}'
    contract = source_constants(PARSER / 'excelToCsv/mjap.py')
    for section, constant in [('outages', 'OUTAGE_COLUMNS'), ('projects', 'PROJECT_COLUMNS')]:
        assert tuple(row[0] for row in data[section]['rows']) == contract[constant]
    assert set(data['reserved_outage_columns']) == contract['RESERVED_OUTAGE_COLUMNS']
    maintenance = source_constants(PARSER / 'excelToCsv/maintenance.py')
    assert tuple(row[0] for row in data['maintenance']['rows']) == maintenance['CSV_COLUMNS']
    for section in data.values():
        if isinstance(section, dict) and 'rows' in section:
            assert all(len(row) == len(section['columns']) for row in section['rows'])


class Diagram:
    def __init__(self, width, height, title):
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img">',
                      f'<title>{html.escape(title)}</title>',
                      f'<rect width="{width}" height="{height}" fill="#f5f8fa" rx="18"/>',
                      '<g font-family="Arial, sans-serif" fill="#173340">']
        self.text(32, 36, title, 24, bold=True)

    def text(self, x, y, value, size=17, bold=False, color='#173340', anchor='start'):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}" text-anchor="{anchor}">{html.escape(value)}</text>')

    def box(self, x, y, width, height, title, lines=(), fill='#e1f1ed'):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="{fill}" stroke="#aac1c8"/>')
        self.text(x + 18, y + 29, title, 19, bold=True)
        for index, line in enumerate(lines):
            self.text(x + 18, y + 57 + index * 24, line, 16)

    def line(self, x1, y1, x2, y2, arrow=True, label=None):
        self.parts.append(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="#335566" stroke-width="2.4" fill="none"/>')
        if arrow:
            distance = math.hypot(x2 - x1, y2 - y1)
            ux, uy = (x2 - x1) / distance, (y2 - y1) / distance
            ax, ay = x2 - 11 * ux, y2 - 11 * uy
            points = f'{x2},{y2} {ax - 5 * uy},{ay + 5 * ux} {ax + 5 * uy},{ay - 5 * ux}'
            self.parts.append(f'<polygon points="{points}" fill="#335566"/>')
        if label:
            x, y = (x1 + x2) / 2, (y1 + y2) / 2 - 9
            width = len(label) * 8.4 + 16
            self.parts.append(f'<rect x="{x - width / 2}" y="{y - 17}" width="{width}" height="22" fill="#f5f8fa"/>')
            self.text(x, y, label, 15, anchor='middle')

    def node(self, x, y, label):
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="27" fill="#ffffff" stroke="#117c77" stroke-width="3"/>')
        self.text(x, y + 6, label, 17, bold=True, anchor='middle')

    def save(self, name):
        result = '\n'.join([*self.parts, '</g></svg>'])
        (DOCS / 'abbildungen' / f'{name}.svg').write_text(result)
        return result


def diagrams():
    folder = DOCS / 'abbildungen'
    folder.mkdir(exist_ok=True)
    result = {}
    d = Diagram(1400, 840, 'Der vollständige Datenfluss – Stand des Codes')
    d.box(30, 90, 255, 115, 'Excel-Netzblatt', ['SUB: Stationen', 'Andere Typen: Elemente'])
    d.box(30, 285, 255, 135, 'Zusätzliche echte Quellen', ['Freischaltungen.csv', 'Projekte.csv', 'Nicht aus Excel abgeleitet'], '#fff0d9')
    d.box(350, 90, 240, 115, 'Parser --mjap', ['Prüfen + ausschließen', 'Restbestand erneut prüfen'])
    d.box(655, 65, 300, 235, 'CSV-Eingabeordner für MJAP', ['Stationen.csv (20 Spalten)', 'Netzelemente.csv (30)', 'Freischaltungen.csv', 'Projekte.csv', 'Komma; UTF-8; TT.MM.JJJJ'])
    d.box(1025, 90, 340, 115, 'MJAP: Visualisierung erstellen', ['Vier CSVs einlesen', 'SO/SK und Attribute erstellen'])
    d.box(1025, 355, 340, 135, 'Interne Dateien + Geometrien', ['SO.csv, SK.csv; attribute.xlsx', 'missing_data.xlsx; SK.log', 'Shapefiles + GeoPackages'], '#e9edf8')
    d.box(655, 355, 300, 135, 'QGIS-Visualisierung', ['Punkte, Linien, Projekte', 'Joins + Stile + Zeitfelder', 'Ergebnisse kontrollieren'])
    d.box(350, 355, 240, 135, 'Projekt speichern', ['QGIS-Projekt als .qgz', 'Datendateien aufbewahren'], '#e9edf8')
    d.box(350, 560, 605, 90, 'Optional danach: Länderkarte ergänzen', ['DE / NL / BE / FR; vorhandene Netzlayer bleiben erhalten'])
    d.line(285, 147, 350, 147)
    d.line(285, 340, 370, 205)
    d.line(590, 147, 655, 147)
    d.line(955, 147, 1025, 147)
    d.line(1195, 205, 1195, 355)
    d.line(1025, 420, 955, 420)
    d.line(655, 420, 590, 420)
    d.line(470, 490, 470, 560)
    d.box(30, 525, 255, 125, 'Aktuelle Grenze', ['Excel allein erzeugt', 'noch kein vollständiges', 'Vier-Tabellen-Paket.'], '#fff0d9')
    d.box(30, 715, 1340, 95, 'Automatischer Teil-Export und Pflege',
          ['Fehler/Warnungen: ganzes Element, abhängige Leitungen und komplette Dreibeine ausschließen.',
           'Fehlerliste.csv + Pflegebericht.html; Exit 0 = sauber, 3 = Teil-Export, 2 = Abbruch.'], '#fff0d9')
    result['ablauf'] = d.save('ablauf')
    mermaid = '''flowchart LR
  E[Excel: ein Netzblatt] --> P[Parser --mjap]
  F[Echte Freischaltungen.csv] --> P
  J[Echte Projekte.csv] --> P
  P --> R[Fehlerliste.csv und Pflegebericht.html]
  P --> A[Elemente mit Befunden und Abhängigkeiten ausschließen]
  A --> C[Vier geprüfte CSVs im Eingabeordner]
  C --> M[MJAP: Visualisierung erstellen]
  M --> Z[SO/SK und XLSX-Zwischenprodukte]
  Z --> G[Geometrien, Layer, Joins, Stile und Zeitfelder]
  G --> Q[QGIS-Projekt speichern]
  Q --> L[Optional: DE/NL/BE/FR ergänzen]
'''
    (folder / 'ablauf.mmd').write_text(mermaid)

    d = Diagram(1400, 680, 'Schlüssel und Beziehungen zwischen den vier Eingabetabellen')
    d.box(40, 100, 465, 165, 'Stationen.csv', ['MJAP-ID = Stationsschlüssel', 'lat / long = Position', 'Kann Anfang, Ende oder Y-Knoten sein'])
    d.box(830, 100, 520, 165, 'Netzelemente.csv', ['MJAP-ID = Elementschlüssel', 'Anfang / Ende / T / Y → Stationen.MJAP-ID', 'Ein Element kann mehrere Legs besitzen'])
    d.box(830, 420, 520, 165, 'Freischaltungen.csv', ['MJAP-ID = Schaltungskennung', 'Netzelement:MJAP-ID → Elementschlüssel', 'Projekt → Projekte.Projektname'])
    d.box(40, 420, 465, 165, 'Projekte.csv', ['Projektname = Projekt-Join-Schlüssel', 'betroffener Standort = Stations-ID-Liste', 'von / bis = Projektzeitraum'])
    d.line(830, 180, 505, 180, label='Anfang / Ende / Y / T')
    d.line(1090, 420, 1090, 265, label='Netzelementreferenz')
    d.line(830, 500, 505, 500, label='Projektname (optional)')
    d.line(270, 420, 270, 265, label='Ein oder mehrere Standorte')
    d.text(40, 635, 'In Excel: Roh-ID Berlin_380. Im Plugin-Paket: vollständige ID Amprion_Berlin_380.', 19, bold=True)
    result['beziehungen'] = d.save('beziehungen')
    (folder / 'beziehungen.mmd').write_text('''erDiagram
  STATIONEN ||--o{ NETZELEMENTE : "Anfang / Ende / T / Y"
  NETZELEMENTE ||--o{ FREISCHALTUNGEN : "Netzelement:MJAP-ID"
  PROJEKTE o|--o{ FREISCHALTUNGEN : "Projektname = Projekt"
  STATIONEN }|--o{ PROJEKTE : "betroffener Standort als ID-Liste"
''')

    d = Diagram(1400, 700, 'Topologie: Excel-Dreibein wird zu einer Y-Zeile und zwei Paarzeilen')
    d.box(30, 80, 420, 100, '1. CSV-Zeile: vollständiges Y', ['Anfang=A / Ende=B / T1=C / Y1=X', 'Name: LONG-NAME der ersten Excel-Zeile'])
    d.box(485, 80, 420, 100, '2. CSV-Zeile: Paar A–C', ['T1/T2/Y1/Y2 leer', 'Namenszusatz: ohne Bein B'])
    d.box(940, 80, 430, 100, '3. CSV-Zeile: Paar B–C', ['T1/T2/Y1/Y2 leer', 'Namenszusatz: ohne Bein A'])
    for x, y in [(90, 250), (390, 250), (240, 425)]: d.line(x, y, 240, 335, False)
    for x, y, label in [(90, 250, 'A'), (390, 250, 'B'), (240, 425, 'C / T1'), (240, 335, 'X / Y1')]: d.node(x, y, label)
    d.line(545, 335, 845, 335, False)
    d.node(545, 335, 'A'); d.node(845, 335, 'C')
    d.line(1000, 335, 1305, 335, False)
    d.node(1000, 335, 'B'); d.node(1305, 335, 'C')
    d.text(240, 490, 'MJAP: drei Y-Teilstrecken', 19, bold=True, anchor='middle')
    d.text(695, 490, 'MJAP: eine direkte Linie', 19, bold=True, anchor='middle')
    d.text(1155, 490, 'MJAP: eine direkte Linie', 19, bold=True, anchor='middle')
    d.box(30, 545, 1340, 115, 'Excel: 3 Beine → CSV: 3 Zeilen → MJAP: 5 Linienobjekte',
          ['Erste Excel-Zeile: A + B + T1=C + Y1=X. Zweite: A–C ohne B. Dritte: B–C ohne A.',
           'Y1 steht nur im ersten Eintrag; T2/Y2 bleiben leer. Paarlinien sind direkte Verbindungen.'], '#fff0d9')
    result['topologie'] = d.save('topologie')
    (folder / 'topologie.mmd').write_text('''flowchart LR
  Excel[Excel: X-A / X-B / X-C] --> Voll[Erste CSV-Zeile: A / B / T1=C / Y1=X]
  Excel --> Paar2[Zweite CSV-Zeile: A-C ohne B]
  Excel --> Paar3[Dritte CSV-Zeile: B-C ohne A]
  subgraph Paar_AC
    A1[A] --- E1[C]
  end
  subgraph Y
    A2[Anfang] --- Y1[Y1]
    E2[B] --- Y1
    T1[C / T1] --- Y1
  end
  subgraph Paar_BC
    B3[B] --- C3[C]
  end
''')

    d = Diagram(1400, 625, 'Betriebsphasen und Schaltungszeiträume beim direkten MJAP-Import')
    d.box(30, 80, 1340, 125, 'Paarweise Listen mit gleicher Länge',
          ['IBN - Mehrfach: 01.01.2025;01.01.2030',
           'ABN - Mehrfach: 31.12.2029;31.12.2035',
           'Nur direkter Plugin-Mehrfachimport; Parser-MJAP-Weg: einzelne Termine.'])
    d.line(180, 300, 1310, 300, False)
    for year, x in [(2025, 180), (2028, 465), (2030, 655), (2035, 1130)]:
        d.line(x, 293, x, 307, False); d.text(x, 335, str(year), anchor='middle')
    d.box(180, 375, 425, 72, 'SK_A: erste Phase', ['2025 bis Ende 2029'])
    d.box(655, 375, 580, 72, 'SK_A_1: zweite Phase', ['2030 bis Ende 2035'])
    d.line(465, 275, 465, 300)
    d.text(345, 260, 'Schaltung 2028 → erste Phase', 18, bold=True)
    d.box(30, 495, 1340, 95, 'Unbekanntes ABN bleibt unbekannt',
          ['Der separate Zeitreihen-SQL-Vergleich schließt NULL-ABN aus. Keine Enddaten erfinden.'], '#fff0d9')
    result['zeit'] = d.save('zeit')
    (folder / 'zeit.mmd').write_text('''flowchart LR
  L[Paarweise IBN-/ABN-Listen] --> P1[SK_A: 2025–2029]
  L --> P2[SK_A_1: 2030–2035]
  S1[Schaltung 2028] --> P1
  S2[Schaltung 2032] --> P2
  N[Unbekanntes ABN] --> Q[NULL-Vergleich im Zeitreihenwerkzeug: kein Treffer]
''')
    return result


def inline(value):
    value = html.escape(value)
    value = re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
    value = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', value)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', value)


def slug(value):
    text = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', text).strip('-')


def render(markdown, figures):
    lines, body, toc = markdown.splitlines(), [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip(): i += 1; continue
        if line.startswith('```'):
            language = line[3:]; block = []; i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                block.append(lines[i]); i += 1
            body.append(f'<pre><code data-language="{html.escape(language)}">{html.escape(chr(10).join(block))}</code></pre>'); i += 1; continue
        heading = re.match(r'^(#{1,3}) (.+)', line)
        if heading:
            level, title = len(heading[1]), heading[2]; target = slug(title)
            body.append(f'<h{level} id="{target}">{inline(title)}</h{level}>')
            if level == 2: toc.append(f'<li><a href="#{target}">{html.escape(title)}</a></li>')
            i += 1; continue
        image = re.fullmatch(r'!\[([^\]]*)\]\(abbildungen/([a-z]+)\.svg\)', line)
        if image:
            body.append(f'<figure>{figures[image[2]]}<figcaption>{html.escape(image[1])}</figcaption></figure>'); i += 1; continue
        if line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [cell.strip() for cell in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', cell) for cell in cells): rows.append(cells)
                i += 1
            head = '<tr>' + ''.join('<th scope="col">' + inline(cell) + '</th>' for cell in rows[0]) + '</tr>'
            content = ''.join('<tr>' + ''.join('<td>' + inline(cell) + '</td>' for cell in row) + '</tr>' for row in rows[1:])
            body.append(f'<div class="table-wrap"><table><thead>{head}</thead><tbody>{content}</tbody></table></div>'); continue
        item = re.match(r'^(\d+\.|-) (.*)', line)
        if item:
            ordered = item[1] != '-'; start = int(item[1][:-1]) if ordered else 1; items = []
            while i < len(lines):
                item = re.match(r'^(\d+\.|-) (.*)', lines[i])
                if not item or (item[1] != '-') != ordered: break
                value = item[2]; i += 1
                while i < len(lines) and lines[i].startswith('  ') and lines[i].strip():
                    value += ' ' + lines[i].strip(); i += 1
                items.append('<li>' + inline(value) + '</li>')
            tag = 'ol' if ordered else 'ul'; attr = f' start="{start}"' if ordered else ''
            body.append(f'<{tag}{attr}>' + ''.join(items) + f'</{tag}>'); continue
        paragraph = [line]; i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r'^(#|\||```|!\[|\d+\. |\- )', lines[i]):
            paragraph.append(lines[i]); i += 1
        body.append('<p>' + inline(' '.join(paragraph)) + '</p>')
    return '\n'.join(body), '\n'.join(toc)


STYLE = '''
:root{color-scheme:light;--ink:#173340;--accent:#116c68;--line:#d6e2e6;--paper:#fff;--muted:#526773}
*{box-sizing:border-box}body{margin:0;background:#f4f7f8;color:var(--ink);font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
.layout{display:grid;grid-template-columns:280px minmax(0,1fr);max-width:1680px;margin:auto}aside{padding:30px 22px;position:sticky;top:0;height:100vh;overflow:auto;border-right:1px solid var(--line)}aside strong{font-size:19px}aside p{font-size:13px;color:var(--muted)}aside ol{padding-left:17px}aside li{margin:12px 0;font-size:13px}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
main{background:var(--paper);padding:36px 48px;min-width:0}h1{font-size:38px;line-height:1.2;letter-spacing:-.025em}h2{font-size:27px;margin-top:56px;padding-top:20px;border-top:2px solid var(--line);scroll-margin-top:15px}h3{font-size:20px;margin-top:30px}p,li{max-width:100ch}strong{font-weight:650}code{font: .91em ui-monospace,SFMono-Regular,Consolas,monospace;background:#edf4f5;padding:2px 4px;border-radius:4px;overflow-wrap:anywhere}pre{background:#173340;color:#f1f7f8;padding:20px;border-radius:10px;overflow:auto;font-size:13px;line-height:1.6}pre code{background:none;color:inherit;padding:0;white-space:pre;overflow-wrap:normal}
.table-wrap{overflow:auto;margin:22px 0;border:1px solid var(--line);border-radius:9px}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.55}th{background:#e5f1ef;text-align:left;font-weight:650;padding:13px;vertical-align:top}td{padding:12px 13px;border-top:1px solid var(--line);vertical-align:top}tbody tr:nth-child(even){background:#f8fafb}td:first-child{font-weight:550}figure{margin:26px 0}figure svg{width:100%;height:auto;display:block}figcaption{font-size:13px;color:var(--muted);margin-top:8px}
@media(max-width:1050px){.layout{grid-template-columns:1fr}aside{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line)}aside ol{columns:2}main{padding:24px}h1{font-size:30px}}
@media print{body{background:#fff;font-size:10pt}.layout{display:block}aside{display:none}main{padding:0}h1{font-size:24pt}h2{font-size:17pt}h3{font-size:13pt}table{font-size:8pt}.table-wrap{overflow:visible;border-radius:0}td,th{padding:5pt}thead{display:table-header-group}tr,figure,pre{break-inside:avoid}pre{white-space:pre-wrap}pre code{white-space:pre-wrap}a{color:inherit}h2,h3{break-after:avoid}figure svg{max-height:160mm}*{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
'''


def main():
    data = json.loads((DOCS / 'datenvertrag.json').read_text())
    validate_inventory(data)
    figures = diagrams()
    content = (DOCS / 'DATENFLUSS_UND_TABELLEN_DE.vorlage.md').read_text()
    for name, section in data.items():
        if isinstance(section, dict) and 'rows' in section:
            columns = '| ' + ' | '.join(section['columns']) + ' |'
            divider = '| ' + ' | '.join('---' for _ in section['columns']) + ' |'
            rows = '\n'.join('| ' + ' | '.join(str(value).replace('|', '/') for value in row) + ' |' for row in section['rows'])
            content = content.replace(f'<!-- TABLE:{name} -->', '\n'.join([columns, divider, rows]))
    for name in figures:
        figure = f'![{name.capitalize()}](abbildungen/{name}.svg)\n\n[Bearbeitbare Mermaid-Quelle](abbildungen/{name}.mmd).'
        content = content.replace(f'<!-- FIG:{name} -->', figure)
    assert '<!-- TABLE:' not in content and '<!-- FIG:' not in content
    content = content.replace("`['380','110']`", '`["380","110"]`')
    (DOCS / 'DATENFLUSS_UND_TABELLEN_DE.md').write_text(content)
    body, toc = render(content, figures)
    document = f'''<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Excel → Parser → MJAP: Datenhandbuch</title><style>{STYLE}</style></head><body><div class="layout"><aside aria-label="Inhaltsverzeichnis"><strong>Datenhandbuch</strong><p>Excel · Parser · MJAP · QGIS<br>Stand 07.10.2026<br>Offline lesbar. Suche mit Strg/Cmd+F; druckbar über den Browser.</p><ol>{toc}</ol></aside><main>{body}</main></div></body></html>'''
    (DOCS / 'DATENFLUSS_UND_TABELLEN_DE.html').write_text(document)
    print('Handbook generated; 13 Excel fields, 20 station fields, 30 element fields, 9 outage fields and 4 project fields checked against source.')


if __name__ == '__main__':
    main()
