"""The single palette.

Qt stylesheets have no variables, so the stylesheet is a template formatted from
these values. Custom-painted widgets read the same object, which is what keeps a
painted stepper node the same blue as a stylesheet-drawn button.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tokens:
    """Colours, metrics and type sizes taken from the interface design."""

    # surfaces
    appBackground: str = "#F2F5F9"
    cardBackground: str = "#FFFFFF"
    cardBorder: str = "#DCE4ED"
    inputBackground: str = "#FFFFFF"
    inputBorder: str = "#CFD9E4"
    headerGradientStart: str = "#EAF3FD"
    headerGradientEnd: str = "#D7E9FA"
    headerMotif: str = "#BCD9F2"

    # brand
    primary: str = "#1668C7"
    primaryHover: str = "#1257A8"
    primaryPressed: str = "#0E4586"
    primarySoft: str = "#E8F1FC"
    titleNavy: str = "#10375E"
    subtitle: str = "#4E7CA8"

    # text
    textPrimary: str = "#1F2933"
    textSecondary: str = "#6B7684"
    textMuted: str = "#98A2AE"
    textOnPrimary: str = "#FFFFFF"

    # status
    success: str = "#21A366"
    successBackground: str = "#EBF8F1"
    successBorder: str = "#BFE6D2"
    warning: str = "#E9A21A"
    warningBackground: str = "#FDF6E7"
    error: str = "#E0433F"
    errorBackground: str = "#FDEDEC"

    # components
    track: str = "#E4E9F0"
    stepperPending: str = "#C7D0DA"
    divider: str = "#E4E9F0"
    scrollHandle: str = "#C7D0DA"

    # metrics, in device-independent pixels
    cardRadius: int = 10
    controlRadius: int = 6
    cardPadding: int = 16
    gridGap: int = 12
    controlHeight: int = 34

    # type
    fontFamily: str = '"Segoe UI", "Segoe UI Variable", -apple-system, "Helvetica Neue", Arial, sans-serif'
    monoFamily: str = '"Cascadia Mono", Consolas, "SF Mono", "Menlo", monospace'
    titleSize: int = 28
    subtitleSize: int = 14
    cardTitleSize: int = 15
    bodySize: int = 13
    smallSize: int = 12


TOKENS = Tokens()
