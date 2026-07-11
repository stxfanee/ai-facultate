"""Compatibility module for older imports.

The maintained implementation lives in server.memory.study_memory.
"""

from __future__ import annotations

import sys

from server.memory import study_memory as _study_memory

sys.modules[__name__] = _study_memory
