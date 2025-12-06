import base64
import hashlib
import os
import secrets
import re
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from starlette.requests import Request

# Optional symmetric encryption for management passwords
_ENC_KEY = os.getenv("ENCRYPTION_KEY")
_f = None

if _ENC_KEY:
    try:
        key_str = _ENC_KEY.strip()
        # Accept either a full Fernet key or derive one from an arbitrary passphrase.
        if len(key_str) >= 44 and key_str.endswith("="):
            fernet_key = key_str.encode()
        else:
            digest = hashlib.sha256(key_str.encode("utf-8")).digest()
            fernet_key = base64.urlsafe_b64encode(digest)
        _f = Fernet(fernet_key)
    except Exception:
        _f = None


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


# ----- Parsing helpers -----

def parse_decimal(value: str) -> Optional[float]:
    """Parse a decimal number allowing comma or dot."""
    if not value:
        return None
    try:
        normalized = value.replace(",", ".").strip()
        return float(normalized)
    except ValueError:
        return None


def parse_ram_mb(value: str) -> Optional[int]:
    """
    Parse RAM with optional unit (MB/GB/TB). Defaults to GB if a unit is missing.
    Returns MB.
    """
    if not value:
        return None
    v = value.strip().lower()
    match = re.match(r"([0-9]+(?:[\\.,][0-9]+)?)(tb|gb|mb)?", v)
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    unit = match.group(2) or "gb"
    if unit == "tb":
        return int(number * 1024 * 1024)
    if unit == "gb":
        return int(number * 1024)
    return int(number)


def parse_storage_gb(value: str) -> Optional[int]:
    """
    Parse storage with optional unit (GB/TB). Defaults to GB.
    Returns GB.
    """
    if not value:
        return None
    v = value.strip().lower()
    match = re.match(r"([0-9]+(?:[\\.,][0-9]+)?)(tb|gb)?", v)
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    unit = match.group(2) or "gb"
    if unit == "tb":
        return int(number * 1024)
    return int(number)


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
