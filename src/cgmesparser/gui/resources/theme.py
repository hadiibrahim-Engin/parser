"""The application stylesheet.

Qt stylesheets cannot reference variables, so the sheet is a template filled
from :mod:`cgmesparser.gui.resources.tokens`. Painted widgets read the same tokens,
which is what keeps a hand-drawn stepper node the same blue as a styled button.

Object names used as selectors are set by the widgets that own them; changing a
name here without changing it there silently drops the styling, so both sides
are kept in this file's vocabulary: ``card``, ``cardTitle``, ``sectionBadge``,
and so on.
"""

from __future__ import annotations

from cgmesparser.gui.resources.tokens import TOKENS, Tokens

_TEMPLATE = """
QWidget {{
    font-family: {fontFamily};
    font-size: {bodySize}px;
    color: {textPrimary};
}}

QMainWindow, QDialog, #rootSurface {{
    background: {appBackground};
}}

QScrollArea, QScrollArea > QWidget > QWidget, #workspaceSurface, #contextRail {{
    background: transparent;
    border: none;
}}

/* ---- cards ------------------------------------------------------------- */

#card {{
    background: {cardBackground};
    border: 1px solid {cardBorder};
    border-radius: {cardRadius}px;
}}

#cardTitle {{
    font-size: {cardTitleSize}px;
    font-weight: 700;
    color: {textPrimary};
}}

#cardDescription {{
    color: {textSecondary};
    font-size: {smallSize}px;
}}

/* ---- header ------------------------------------------------------------ */

#headerBanner {{
    background: {cardBackground};
    border-bottom: 1px solid {cardBorder};
}}

#headerTitle {{
    font-size: {titleSize}px;
    font-weight: 700;
    color: {titleNavy};
}}

#headerSubtitle {{
    font-size: {subtitleSize}px;
    color: {textSecondary};
}}

/* ---- inputs ------------------------------------------------------------ */

#inputLabel {{
    color: {textPrimary};
    font-weight: 600;
}}

#inputSourceRow {{
    background: {inputBackground};
    border: 1px solid {cardBorder};
    border-radius: {controlRadius}px;
}}

#inputSourceRow:hover {{
    border-color: {inputBorder};
    background: {cardBackground};
}}

QLineEdit {{
    background: {cardBackground};
    border: 1px solid {inputBorder};
    border-radius: {controlRadius}px;
    padding: 0 10px;
    min-height: {controlHeight}px;
    selection-background-color: {primary};
    selection-color: {textOnPrimary};
}}

QLineEdit:focus {{
    border: 2px solid {primary};
}}

QLineEdit:disabled {{
    background: {appBackground};
    color: {textMuted};
}}

/* A path field while something droppable hovers over its row. */
QLineEdit[dropActive="true"] {{
    border: 2px dashed {primary};
    background: {primarySoft};
}}

/* ---- buttons ----------------------------------------------------------- */

QPushButton {{
    background: {cardBackground};
    border: 1px solid {inputBorder};
    border-radius: {controlRadius}px;
    padding: 0 15px;
    min-height: {controlHeight}px;
    color: {textPrimary};
}}

QPushButton:hover {{
    background: {primarySoft};
    border-color: {primary};
}}

QPushButton#browseButton {{
    background: {primarySoft};
    border-color: transparent;
    color: {primary};
    font-weight: 600;
}}

QPushButton#browseButton:hover {{
    background: {primary};
    border-color: {primary};
    color: {textOnPrimary};
}}

QPushButton:pressed {{
    background: {track};
}}

QPushButton:disabled {{
    background: {appBackground};
    border-color: {cardBorder};
    color: {textMuted};
}}

QPushButton#primaryButton {{
    background: {primary};
    border: 1px solid {primary};
    color: {textOnPrimary};
    font-weight: 600;
}}

QPushButton#primaryButton:hover {{
    background: {primaryHover};
    border-color: {primaryHover};
}}

QPushButton#primaryButton:pressed {{
    background: {primaryPressed};
    border-color: {primaryPressed};
}}

QPushButton#primaryButton:disabled {{
    background: {track};
    border-color: {cardBorder};
    color: {textMuted};
}}

QPushButton#accentButton {{
    color: {primary};
    border: 1px solid {primary};
    font-weight: 600;
}}

QPushButton#accentButton:disabled {{
    color: {textMuted};
    border-color: {cardBorder};
}}

QPushButton#linkButton {{
    background: {primarySoft};
    border: 1px solid transparent;
    color: {primary};
    font-weight: 600;
}}

QPushButton#linkButton:disabled {{
    background: {appBackground};
    border-color: transparent;
    color: {textMuted};
}}

QPushButton#ghostButton {{
    background: transparent;
    border: 1px solid transparent;
    color: {textSecondary};
}}

/* ---- validation strip -------------------------------------------------- */

#validationStrip {{
    border-radius: 10px;
    border: 1px solid {successBorder};
    background: {successBackground};
}}

#validationStrip[tone="neutral"] {{
    border-color: {cardBorder};
    background: {inputBackground};
}}

#validationStrip[tone="error"] {{
    border-color: {error};
    background: {errorBackground};
}}

#validationVerdict {{
    font-size: {cardTitleSize}px;
    font-weight: 600;
    color: {success};
}}

#validationVerdict[tone="neutral"] {{
    color: {textSecondary};
}}

#validationVerdict[tone="error"] {{
    color: {error};
}}

#checkText {{
    color: {textPrimary};
    font-size: {smallSize}px;
}}

#checkText[tone="ok"] {{
    color: {success};
}}

#checkText[tone="warning"] {{
    color: {warning};
}}

#checkText[tone="error"] {{
    color: {error};
}}

/* ---- processing -------------------------------------------------------- */

QProgressBar {{
    background: {track};
    border: none;
    border-radius: 6px;
    min-height: 9px;
    max-height: 9px;
    text-align: center;
}}

QProgressBar::chunk {{
    background: {primary};
    border-radius: 6px;
}}

#progressLabel {{
    color: {primary};
    font-weight: 700;
}}

#processingStatus {{
    background: {inputBackground};
    border: 1px solid {cardBorder};
    border-radius: {controlRadius}px;
}}

#statusCaption {{
    color: {textMuted};
    font-size: 10px;
    font-weight: 700;
}}

#statusText {{
    color: {primary};
    font-weight: 700;
}}

/* ---- messages ---------------------------------------------------------- */

QTabWidget::pane {{
    border: none;
    top: -1px;
}}

QTabBar::tab {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 7px 12px 9px 4px;
    margin-right: 10px;
    color: {textSecondary};
}}

QTabBar::tab:selected {{
    color: {primary};
    border-bottom: 2px solid {primary};
    font-weight: 600;
}}

QTabBar::tab:hover:!selected {{
    color: {textPrimary};
}}

QTableView {{
    background: {inputBackground};
    border: 1px solid {cardBorder};
    border-radius: {controlRadius}px;
    gridline-color: transparent;
    selection-background-color: {primarySoft};
    selection-color: {textPrimary};
}}

QTableView::item {{
    padding: 4px 5px;
    border: none;
}}

#messageEmpty {{
    color: {textMuted};
}}

/* ---- key / value rows -------------------------------------------------- */

#keyValueRow {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {divider};
    border-radius: 0;
}}

#keyLabel {{
    color: {textSecondary};
}}

#keySeparator {{
    color: {textMuted};
}}

#valueLabel {{
    font-weight: 700;
    color: {titleNavy};
}}

#valueLabel[empty="true"] {{
    font-weight: 400;
    color: {textMuted};
}}

/* ---- action bar -------------------------------------------------------- */

#actionBar {{
    background: {cardBackground};
    border-top: 1px solid {cardBorder};
}}

#actionBar QPushButton {{
    min-height: 40px;
    font-size: 13px;
}}

/* ---- scrollbars -------------------------------------------------------- */

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: {scrollHandle};
    border-radius: 4px;
    min-height: 28px;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background: {scrollHandle};
    border-radius: 4px;
    min-width: 28px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ---- dialogs ----------------------------------------------------------- */

QGroupBox {{
    background: {cardBackground};
    border: 1px solid {cardBorder};
    border-radius: {cardRadius}px;
    margin-top: 10px;
    padding: 14px 12px 10px 12px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {textSecondary};
}}

QSpinBox {{
    background: {inputBackground};
    border: 1px solid {inputBorder};
    border-radius: {controlRadius}px;
    padding: 0 8px;
    min-height: {controlHeight}px;
}}

QCheckBox {{
    spacing: 8px;
}}

QDialogButtonBox QPushButton {{
    min-width: 96px;
}}

QToolTip {{
    background: {textPrimary};
    color: {cardBackground};
    border: none;
    padding: 5px 8px;
}}
"""


def buildStylesheet(tokens: Tokens = TOKENS) -> str:
    """Render the stylesheet for a palette."""
    return _TEMPLATE.format(**{field: getattr(tokens, field) for field in tokens.__slots__})
