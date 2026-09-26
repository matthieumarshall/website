"""Password hashing with bcrypt (SHA-256 pre-hashed to avoid the 72-byte limit)."""

import base64
import hashlib

import bcrypt


def _prepare(plain_password: str) -> bytes:
    """SHA-256 pre-hash so bcrypt's 72-byte limit is never hit."""
    digest = hashlib.sha256(plain_password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash of *plain_password*."""
    return bcrypt.hashpw(_prepare(plain_password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if *plain_password* matches *hashed_password*."""
    return bcrypt.checkpw(_prepare(plain_password), hashed_password.encode("utf-8"))
