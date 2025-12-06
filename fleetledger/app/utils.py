import os
import secrets
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from starlette.requests import Request

# Optional symmetric encryption for management passwords
_ENC_KEY = os.getenv("ENCRYPTION_KEY")
_f = None

if _ENC_KEY:
    # If the key is already a valid Fernet key string, use it directly.
    # Otherwise you could do more validation/derivation, but for now we assume a proper key.
    _f = Fernet(
        _ENC_KEY.encode() if not _ENC_KEY.strip().endswith("=") else _ENC_KEY
    )


def can_encrypt() -> bool:
    """Return True if an encryption key has been configured."""
    return _f is not None


def encrypt_secret(plaintext: str) -> Optional[str]:
    """Encrypt a secret string using Fernet, if configured."""
    if not plaintext or not _f:
        return None
    token = _f.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_secret(token: str) -> Optional[str]:
    """Decrypt a Fernet-encrypted token, returning a string or None."""
    if not token or not _f:
        return None
    try:
        plaintext = _f.decrypt(token.encode("utf-8"))
        return plaintext.decode("utf-8")
    except (InvalidToken, ValueError):
        return None


# ----- CSRF helpers -----
_CSRF_SESSION_KEY = "csrf_token"


def ensure_csrf_token(request: Request) -> str:
    """
    Ensure the current session has a CSRF token and return it.
    """
    token = request.session.get(_CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[_CSRF_SESSION_KEY] = token
    return token


def validate_csrf(request: Request, token: str) -> bool:
    """
    Compare provided token with the one stored in the session.
    """
    stored = request.session.get(_CSRF_SESSION_KEY)
    if not stored or not token:
        return False
    return secrets.compare_digest(str(stored), str(token))
