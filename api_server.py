"""Compatibility entry point for uvicorn and older imports.

The maintained FastAPI app lives in server.api.api_server.
"""

from __future__ import annotations

import sys

from server.api import api_server as _api_server

sys.modules[__name__] = _api_server
