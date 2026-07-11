"""Compatibility module for apps.launcher.launcher."""

from __future__ import annotations

import sys

from apps.launcher import launcher as _launcher

sys.modules[__name__] = _launcher
