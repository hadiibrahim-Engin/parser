"""The single source of truth for the application version.

``pyproject.toml`` carries the same string; ``tests/gui/testVersion.py`` asserts
that the two never drift apart, and the release scripts update both together.
"""

from __future__ import annotations

__version__ = "0.1.0"

APPLICATION_NAME = "CGMES MJAP Interface"
ORGANISATION_NAME = "MJAP"
