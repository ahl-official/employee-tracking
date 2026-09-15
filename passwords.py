"""Password hashing with legacy plaintext upgrade on login."""

from __future__ import annotations

import hashlib
import secrets


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000).hex()
    return f"pbkdf2:{salt}:{digest}"


def verify_password(password: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("pbkdf2:"):
        try:
            _, salt, digest = stored.split(":", 2)
        except ValueError:
            return False
        check = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000
        ).hex()
        return secrets.compare_digest(check, digest)
    return secrets.compare_digest(password, stored)


def needs_rehash(stored: str) -> bool:
    return not (stored or "").startswith("pbkdf2:")
