"""Compatibility entry point for Streamlit and older imports.

The maintained Streamlit app lives in apps.web.app.
"""

from __future__ import annotations

import sys

from apps.web import app as _app

sys.modules[__name__] = _app
