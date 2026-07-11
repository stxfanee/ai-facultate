"""Compatibility module for older imports.

The maintained implementation lives in server.queue.request_queue.
"""

from __future__ import annotations

import sys

from server.queue import request_queue as _request_queue

sys.modules[__name__] = _request_queue
