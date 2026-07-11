"""Compatibility module for apps.legacy_client.launcher."""

from __future__ import annotations

import sys

from apps.legacy_client import launcher as _launcher

sys.modules[__name__] = _launcher
