"""The single palette.

Qt stylesheets have no variables, so the stylesheet is a template formatted from
these values. Custom-painted widgets read the same object, which is what keeps a
painted stepper node the same blue as a stylesheet-drawn button.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tokens:
    """Colours, metrics and type sizes for the desktop workspace."""

    # surfaces
    appBackground: str = "#F4F7FB"
    cardBackground: str = "#FFFFFF"
    cardBorder: str = "#D9E3EE"
    inputBackground: str = "#FBFCFE"
    inputBorder: str = "#C9D6E3"
    headerGradientStart: str = "#102F4F"
    headerGradientEnd: str = "#174C78"
    headerMotif: str = "#6C98BA"

    # brand
    primary: str = "#1769E0"
    primaryHover: str = "#0F5BC7"
    primaryPressed: str = "#0B49A2"
    primarySoft: str = "#EAF2FF"
    titleNavy: str = "#102F4F"
    subtitle: str = "#C6D9EA"

    # text
    textPrimary: str = "#172536"
    textSecondary: str = "#5D6D7E"
    textMuted: str = "#8A99A8"
    textOnPrimary: str = "#FFFFFF"

    # status
    success: str = "#17875B"
    successBackground: str = "#EBF8F2"
    successBorder: str = "#B9E3D1"
    warning: str = "#D98A0B"
    warningBackground: str = "#FFF7E6"
    error: str = "#D94040"
    errorBackground: str = "#FFF0F0"

    # components
    track: str = "#E4EAF1"
    stepperPending: str = "#BCC9D6"
    divider: str = "#E7ECF2"
    scrollHandle: str = "#B9C6D3"

    # metrics, in device-independent pixels
    cardRadius: int = 14
    controlRadius: int = 8
    cardPadding: int = 20
    gridGap: int = 14
    controlHeight: int = 38

    # type
    fontFamily: str = '"Segoe UI", "Segoe UI Variable", -apple-system, "Helvetica Neue", Arial, sans-serif'
    monoFamily: str = '"Cascadia Mono", Consolas, "SF Mono", "Menlo", monospace'
    titleSize: int = 23
    subtitleSize: int = 12
    cardTitleSize: int = 16
    bodySize: int = 13
    smallSize: int = 12


TOKENS = Tokens()
