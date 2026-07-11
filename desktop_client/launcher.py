"""Compatibility module for apps.client.launcher."""

from __future__ import annotations

import sys

from apps.client import launcher as _launcher

sys.modules[__name__] = _launcher
