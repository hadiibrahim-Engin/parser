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

QScrollArea, QScrollArea > QWidget > QWidget {{
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
    font-weight: 600;
    color: {textPrimary};
}}

#cardTitleAccent {{
    font-size: {cardTitleSize}px;
    font-weight: 600;
    color: {primary};
}}

#sectionBadge {{
    background: {primary};
    color: {textOnPrimary};
    border-radius: 5px;
    font-size: {smallSize}px;
    font-weight: 700;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
}}

/* ---- header ------------------------------------------------------------ */

#headerTitle {{
    font-size: {titleSize}px;
    font-weight: 700;
    color: {titleNavy};
}}

#headerSubtitle {{
    font-size: {subtitleSize}px;
    color: {subtitle};
}}

/* ---- inputs ------------------------------------------------------------ */

#inputLabel {{
    color: {textPrimary};
}}

QLineEdit {{
    background: {inputBackground};
    border: 1px solid {inputBorder};
    border-radius: {controlRadius}px;
    padding: 0 10px;
    min-height: {controlHeight}px;
    selection-background-color: {primary};
    selection-color: {textOnPrimary};
}}

QLineEdit:focus {{
    border: 1px solid {primary};
}}

QLineEdit:disabled {{
    background: {appBackground};
    color: {textMuted};
}}

/* ---- buttons ----------------------------------------------------------- */

QPushButton {{
    background: {cardBackground};
    border: 1px solid {inputBorder};
    border-radius: {controlRadius}px;
    padding: 0 14px;
    min-height: {controlHeight}px;
    color: {textPrimary};
}}

QPushButton:hover {{
    background: {primarySoft};
    border-color: {primary};
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
    background: transparent;
    border: 1px solid {primary};
    color: {primary};
    font-weight: 600;
}}

QPushButton#linkButton:disabled {{
    border-color: {cardBorder};
    color: {textMuted};
}}

QPushButton#ghostButton {{
    background: transparent;
    border: 1px solid {inputBorder};
}}

/* ---- validation strip -------------------------------------------------- */

#validationStrip {{
    border-radius: {controlRadius}px;
    border: 1px solid {successBorder};
    background: {successBackground};
}}

#validationStrip[tone="neutral"] {{
    border-color: {cardBorder};
    background: {appBackground};
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

/* ---- processing -------------------------------------------------------- */

QProgressBar {{
    background: {track};
    border: none;
    border-radius: 6px;
    min-height: 12px;
    max-height: 12px;
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

#statusCaption {{
    color: {primary};
    font-weight: 600;
}}

#statusText {{
    color: {textPrimary};
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
    padding: 6px 14px 8px 4px;
    margin-right: 14px;
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
    background: {cardBackground};
    border: 1px solid {cardBorder};
    border-radius: {controlRadius}px;
    gridline-color: transparent;
    selection-background-color: {primarySoft};
    selection-color: {textPrimary};
}}

QTableView::item {{
    padding: 3px 4px;
    border: none;
}}

#messageEmpty {{
    color: {textMuted};
}}

/* ---- key / value rows -------------------------------------------------- */

#keyLabel {{
    color: {textPrimary};
}}

#keySeparator {{
    color: {textMuted};
}}

#valueLabel {{
    font-weight: 700;
    color: {textPrimary};
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
    min-height: 42px;
    font-size: 14px;
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
    border: 1px solid {cardBorder};
    border-radius: {controlRadius}px;
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
