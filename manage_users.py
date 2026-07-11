"""Compatibility entry point for user management helpers.

The maintained implementation lives in server.users.manage_users.
"""

from __future__ import annotations

import sys

from server.users import manage_users as _manage_users

sys.modules[__name__] = _manage_users
