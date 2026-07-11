"""Compatibility module for apps.desktop.launcher."""

from __future__ import annotations

import sys

from apps.desktop import launcher as _launcher

sys.modules[__name__] = _launcher
