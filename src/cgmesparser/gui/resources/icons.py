"""Vector icons, held as SVG source and tinted on demand.

Each icon carries a ``__C__`` placeholder wherever the accent colour belongs, so
one definition serves every colour the interface needs. Rendered pixmaps are
cached per (name, colour, size, device pixel ratio).
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_COLOUR_PLACEHOLDER = "__C__"

_STROKE = (
    'fill="none" stroke="__C__" stroke-width="1.7" '
    'stroke-linecap="round" stroke-linejoin="round"'
)

_ICONS: dict[str, str] = {
    # --- brand ---------------------------------------------------------------
    "tower": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <path d="M12 2.5V21"/><path d="M12 2.5 6 21"/><path d="M12 2.5 18 21"/>
        <path d="M8.7 6.2h6.6"/><path d="M7.6 11h8.8"/><path d="M6.6 16h10.8"/>
        <path d="M4 21h16"/></g></svg>""",
    # --- input roles ---------------------------------------------------------
    "zip": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>
        <path d="M14 3v5h5"/><path d="M10.6 5.2h1.8"/><path d="M10.6 8h1.8"/>
        <path d="M10.6 10.8h1.8"/><path d="M10.6 13.6h1.8"/></g></svg>""",
    "database": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <ellipse cx="12" cy="5.6" rx="7" ry="2.9"/>
        <path d="M5 5.6v6c0 1.6 3.1 2.9 7 2.9s7-1.3 7-2.9v-6"/>
        <path d="M5 11.6v6.2c0 1.6 3.1 2.9 7 2.9s7-1.3 7-2.9v-6.2"/></g></svg>""",
    "folder": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <path d="M3 7.4a2 2 0 0 1 2-2h3.6l2 2.2H19a2 2 0 0 1 2 2v8.4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
        </g></svg>""",
    "folderOpen": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <path d="M3 8V6.4a2 2 0 0 1 2-2h3.4l2 2.2H18a2 2 0 0 1 2 2V10"/>
        <path d="M3.4 10h17.2l-2.1 8.2a1.6 1.6 0 0 1-1.6 1.2H5.7a1.6 1.6 0 0 1-1.6-1.2z"/></g></svg>""",
    # --- status, drawn filled so they read at 16px ----------------------------
    "checkCircle": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="10" fill="__C__"/>
        <path d="M7.6 12.4l2.9 2.9 5.9-6" fill="none" stroke="#FFFFFF" stroke-width="2"
        stroke-linecap="round" stroke-linejoin="round"/></svg>""",
    "warningTriangle": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 3.2 22 20H2z" fill="__C__"/>
        <path d="M12 9.6v4.2" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/>
        <circle cx="12" cy="17" r="1.15" fill="#FFFFFF"/></svg>""",
    "errorCircle": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="10" fill="__C__"/>
        <path d="M8.9 8.9l6.2 6.2M15.1 8.9l-6.2 6.2" stroke="#FFFFFF" stroke-width="2"
        stroke-linecap="round"/></svg>""",
    "info": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <circle cx="12" cy="12" r="10" fill="__C__"/>
        <circle cx="12" cy="7.9" r="1.2" fill="#FFFFFF"/>
        <path d="M12 11.2v5.4" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"/></svg>""",
    # --- output summary ------------------------------------------------------
    "excel": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>
        <path d="M14 3v5h5"/></g>
        <path d="M9.1 11.9l4.1 5.3M13.2 11.9l-4.1 5.3" fill="none" stroke="__C__"
        stroke-width="1.7" stroke-linecap="round"/></svg>""",
    "lines": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <circle cx="12" cy="4.4" r="2"/><circle cx="4.8" cy="19" r="2"/><circle cx="19.2" cy="19" r="2"/>
        <path d="M12 6.4v5.4"/><path d="M12 11.8 6 17.6"/><path d="M12 11.8 18 17.6"/></g></svg>""",
    "substation": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <path d="M3.2 20h17.6"/><path d="M4.8 20V9.6L12 4.6l7.2 5V20"/>
        <path d="M8.6 20v-6.2"/><path d="M12 20v-6.2"/><path d="M15.4 20v-6.2"/></g></svg>""",
    "clock": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <circle cx="12" cy="12" r="8.8"/><path d="M12 6.9V12l3.4 2"/></g></svg>""",
    # --- actions -------------------------------------------------------------
    "gear": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <circle cx="12" cy="12" r="3.2"/><circle cx="12" cy="12" r="7.4"/>
        <path d="M12 2.4v2.2M12 19.4v2.2M2.4 12h2.2M19.4 12h2.2"/>
        <path d="M5.2 5.2l1.6 1.6M17.2 17.2l1.6 1.6"/>
        <path d="M18.8 5.2l-1.6 1.6M6.8 17.2l-1.6 1.6"/></g></svg>""",
    "checkBadge": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <circle cx="12" cy="12" r="8.8"/><path d="M8.2 12.3l2.7 2.7 5-5.2"/></g></svg>""",
    "play": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M8.2 5.6a.9.9 0 0 1 1.37-.77l9 6.4a.9.9 0 0 1 0 1.54l-9 6.4A.9.9 0 0 1 8.2 18.4z"
        fill="__C__"/></svg>""",
    "stop": """<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <rect x="6.4" y="6.4" width="11.2" height="11.2" rx="1.8" fill="__C__"/></svg>""",
    "exit": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <path d="M14.6 3.6H6.4a1.8 1.8 0 0 0-1.8 1.8v13.2a1.8 1.8 0 0 0 1.8 1.8h8.2"/>
        <path d="M15.2 15.6 19.4 12l-4.2-3.6"/><path d="M19.4 12H9.6"/></g></svg>""",
    "trash": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <path d="M4.6 6.6h14.8"/><path d="M9.4 6.6V5.2a1.4 1.4 0 0 1 1.4-1.4h2.4a1.4 1.4 0 0 1 1.4 1.4v1.4"/>
        <path d="M6.6 6.6v12a1.8 1.8 0 0 0 1.8 1.8h7.2a1.8 1.8 0 0 0 1.8-1.8v-12"/>
        <path d="M10.4 10.6v5.6"/><path d="M13.6 10.6v5.6"/></g></svg>""",
    "chevronDown": f"""<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><g {_STROKE}>
        <path d="M6.6 9.4 12 14.8l5.4-5.4"/></g></svg>""",
}


def availableIcons() -> tuple[str, ...]:
    """Every icon name this module can render."""
    return tuple(sorted(_ICONS))


def svgSource(name: str, colour: str) -> str:
    """The SVG text for ``name``, tinted with ``colour``."""
    try:
        template = _ICONS[name]
    except KeyError:
        raise KeyError(f"Unknown icon {name!r}. Available: {', '.join(availableIcons())}") from None
    return template.replace(_COLOUR_PLACEHOLDER, colour)


@lru_cache(maxsize=512)
def iconPixmap(name: str, colour: str, size: int = 20, ratio: float = 1.0) -> QPixmap:
    """Render one icon to a pixmap at the given device pixel ratio."""
    pixels = max(1, int(round(size * ratio)))
    pixmap = QPixmap(pixels, pixels)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    renderer = QSvgRenderer(QByteArray(svgSource(name, colour).encode("utf-8")))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    return pixmap


@lru_cache(maxsize=512)
def icon(name: str, colour: str, size: int = 20) -> QIcon:
    """A QIcon for ``name`` in ``colour``.

    Two device pixel ratios are baked in so the icon stays sharp when the window
    moves between a standard and a high-DPI display.
    """
    result = QIcon()
    for ratio in (1.0, 2.0):
        result.addPixmap(iconPixmap(name, colour, size, ratio))
    return result
