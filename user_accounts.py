"""Compatibility module for older imports.

The maintained implementation lives in server.users.user_accounts.
"""

from __future__ import annotations

import sys

from server.users import user_accounts as _user_accounts

sys.modules[__name__] = _user_accounts
