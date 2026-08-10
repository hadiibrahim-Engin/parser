"""CGMES MJAP Interface - umbrella package.

This package holds the desktop interface in :mod:`cgmesparser.gui` and, once it
arrives, the CGMES/CIMLA conversion source code in its own sibling folders here
(for example ``cgmesparser/domain``, ``cgmesparser/mapping``). The two do not
import each other's internals - the only contact point is the
:class:`~cgmesparser.gui.services.protocol.ConversionService` Protocol.

Nothing is re-exported here: import from ``cgmesparser.gui`` or from the
relevant converter subpackage directly.
"""

from __future__ import annotations
