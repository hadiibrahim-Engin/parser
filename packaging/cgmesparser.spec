# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the CGMES MJAP Interface.

One file, no console window. There are no data files to bundle: icons and the
stylesheet are Python source, so a missing asset is an import error at build
time rather than a blank icon in front of a user.
"""

import sys
from pathlib import Path

projectRoot = Path(SPECPATH).resolve().parent  # noqa: F821 - injected by PyInstaller
sourceRoot = projectRoot / "src"
sys.path.insert(0, str(sourceRoot))

from cgmesparser.gui.version import __version__  # noqa: E402

iconFile = projectRoot / "build" / "appIcon.ico"
executableName = f"CGMES-MJAP-Interface-{__version__}"

# Qt ships far more than this application uses. Excluding the large optional
# modules roughly halves the executable; everything listed here is verified as
# unused by the import graph.
excludedModules = [
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "tkinter",
    "unittest",
    "pydoc",
]

analysis = Analysis(  # noqa: F821
    [str(sourceRoot / "cgmesparser" / "gui" / "__main__.py")],
    pathex=[str(sourceRoot)],
    binaries=[],
    datas=[],
    hiddenimports=["cgmesparser.gui", "PySide6.QtSvg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludedModules,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)  # noqa: F821

executable = EXE(  # noqa: F821
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name=executableName,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,  # no console window behind the interface
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(iconFile) if iconFile.exists() else None,
)
