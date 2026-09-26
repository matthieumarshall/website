"""Login brute-force protection (slowapi).

The limiter is created at import time because slowapi applies limits with a
route decorator; :func:`website.main.create_app` disables it under test.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
LOGIN_RATE_LIMIT = "5/15minutes"
