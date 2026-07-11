"""Compatibility module for older imports.

The maintained implementation lives in server.config.deployment.
"""

from __future__ import annotations

import sys

from server.config import deployment as _deployment

sys.modules[__name__] = _deployment
