"""The layer between the widgets and the conversion backend.

The controller owns application state and the worker thread. It never imports a
widget; the main window subscribes to its signals.
"""
