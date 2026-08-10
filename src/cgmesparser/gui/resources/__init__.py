"""Design tokens, stylesheet and icons.

Everything here is Python source rather than data files on disk. That keeps the
PyInstaller build a genuine single file with no ``--add-data`` paths to get
wrong, and means a missing asset is an import error at build time rather than a
blank icon at run time.
"""

from __future__ import annotations

from cgmesparser.gui.resources.icons import icon, iconPixmap
from cgmesparser.gui.resources.theme import buildStylesheet
from cgmesparser.gui.resources.tokens import TOKENS, Tokens

__all__ = ["TOKENS", "Tokens", "buildStylesheet", "icon", "iconPixmap"]
