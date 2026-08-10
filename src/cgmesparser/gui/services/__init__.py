"""The boundary between the interface and the conversion backend.

The application depends only on the :class:`~cgmesparser.gui.services.protocol.ConversionService`
Protocol. The real CGMES / CIMLA implementation is added here later without the
interface, the controller or the core changing.
"""
