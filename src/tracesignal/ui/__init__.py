"""Trace Signal user interface: the Signal Hub entry point.

The only package under ``tracesignal`` that imports Streamlit. ``render()`` draws the whole app on the current
page and never calls ``st.set_page_config``; the standalone ``app.py`` or Signal Hub owns the page config.
"""

from tracesignal import __version__
from tracesignal.ui import signal_theme
from tracesignal.ui.app import render

APP_INFO = {"product": "Trace Signal", "version": __version__, "repo": "journey-path-analysis", "slug": "trace"}

__all__ = ["APP_INFO", "render", "signal_theme"]
