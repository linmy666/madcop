"""cc-haha compatibility layer split helpers.

Full route registration remains in ``madcop.server.madcop_compat.register``;
shared pure helpers live here so they can be unit-tested without FastAPI.
"""
from madcop.server.compat.fs_guard import (
    FS_SENSITIVE_PATHS,
    check_path_allowed,
)

__all__ = ["FS_SENSITIVE_PATHS", "check_path_allowed"]
