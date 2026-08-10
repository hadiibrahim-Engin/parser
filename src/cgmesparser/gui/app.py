"""Application entry point.

Composes the object graph - settings store, service, controller, window - and
starts the event loop. This is the only module that decides which conversion
service is in use, which is what makes swapping in the real backend a
one-line change here rather than a search through the interface.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from cgmesparser.gui.controller.conversion import ConversionController
from cgmesparser.gui.core.session import SessionInfo
from cgmesparser.gui.core.states import MessageLevel
from cgmesparser.gui.mainWindow import MainWindow
from cgmesparser.gui.resources.theme import buildStylesheet
from cgmesparser.gui.resources.tokens import TOKENS
from cgmesparser.gui.services.protocol import ConversionService
from cgmesparser.gui.services.unimplemented import UnimplementedConversionService
from cgmesparser.gui.settingsStore import SettingsStore
from cgmesparser.gui.version import APPLICATION_NAME, ORGANISATION_NAME, __version__


def buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cgmes-parser",
        description=f"{APPLICATION_NAME} - CGMES / CIMLA processing and Excel export.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run with a demonstration backend that performs no conversion and writes no files",
    )
    parser.add_argument("--version", action="version", version=f"{APPLICATION_NAME} {__version__}")
    return parser


def createApplication(argv: Sequence[str] | None = None) -> QApplication:
    """Create the QApplication with identity, icon and stylesheet applied."""
    existing = QApplication.instance()
    application = existing if isinstance(existing, QApplication) else QApplication(list(argv or []))

    application.setApplicationName(APPLICATION_NAME)
    application.setApplicationDisplayName(APPLICATION_NAME)
    application.setOrganizationName(ORGANISATION_NAME)
    application.setApplicationVersion(__version__)
    application.setStyle("Fusion")
    application.setStyleSheet(buildStylesheet(TOKENS))
    return application


def buildService(demo: bool) -> ConversionService:
    """Choose the conversion backend.

    The default refuses to pretend a conversion happened. The demo backend is
    reachable only by explicit request, and writes nothing.
    """
    if demo:
        from cgmesparser.gui.services.demo import DemoConversionService

        return DemoConversionService()
    return UnimplementedConversionService()


def buildWindow(service: ConversionService, store: SettingsStore | None = None) -> MainWindow:
    """Assemble the controller and window against ``service``."""
    settingsStore = store if store is not None else SettingsStore()
    preferences = settingsStore.loadPreferences()
    request = settingsStore.loadRequest(rememberPaths=preferences.rememberPaths)

    controller = ConversionController(service, request)
    window = MainWindow(
        controller=controller,
        settingsStore=settingsStore,
        sessionInfo=SessionInfo.capture(PYSIDE_VERSION),
        preferences=preferences,
    )

    controller.log(MessageLevel.INFO, f"{APPLICATION_NAME} {__version__} started.")
    if preferences.rememberPaths and request.paths():
        restored = sum(1 for path in request.paths().values() if path is not None)
        if restored:
            controller.log(MessageLevel.INFO, f"Settings restored ({restored} path(s)).")
    return window


def main(argv: Sequence[str] | None = None) -> int:
    """Run the application. Returns the process exit code."""
    arguments = buildParser().parse_args(list(argv) if argv is not None else None)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    application = createApplication(sys.argv[:1])

    service = buildService(demo=arguments.demo)
    window = buildWindow(service)
    if arguments.demo:
        window.messagesCard.append(
            _demoBanner(),
        )
    window.show()
    return application.exec()


def _demoBanner():
    from cgmesparser.gui.core.result import LogRecord
    from cgmesparser.gui.services.demo import DEMO_BANNER

    return LogRecord.now(MessageLevel.WARNING, DEMO_BANNER)
if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
