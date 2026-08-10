"""Framework-free application core.

Nothing in this package imports Qt. Validation, the state machine and the button
matrix are plain Python so they can be exercised without a ``QApplication``, and
so that the rules they encode are readable without knowing Qt.
"""
