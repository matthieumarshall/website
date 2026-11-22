"""Request limits for login and public health endpoints (slowapi).

The limiter is created at import time because slowapi applies limits with a
route decorator; :func:`website.main.create_app` disables it under test.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
LOGIN_RATE_LIMIT = "5/15minutes"
HEALTH_RATE_LIMIT = "120/minute"
STATUS_RATE_LIMIT = "120/minute"
HEALTH_GLOBAL_RATE_LIMIT = "3600/minute"
STATUS_GLOBAL_RATE_LIMIT = "1800/minute"


def global_rate_key() -> str:
    """Use one shared bucket for all clients on a single application process."""
    return "global"
