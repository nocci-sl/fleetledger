from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlmodel import Session, select

from .db import get_session
from .models import User

# bcrypt_sha256 erlaubt auch längere Passwörter (hashing von SHA-256 vor bcrypt)
pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[User]:
    """
    Retrieve the currently logged-in user based on the session cookie.

    Returns None if no user is logged in or the user is inactive.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = session.get(User, user_id)
    if not user or not user.is_active:
        # Clear session if the user was deactivated.
        request.session.clear()
        return None
    return user


def require_current_user(
    current_user: Optional[User] = Depends(get_current_user),
) -> User:
    """
    Require an authenticated user.

    If not authenticated, redirect to /login with a 303 status.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return current_user


def require_admin(
    current_user: Optional[User] = Depends(get_current_user),
) -> User:
    """
    Require an authenticated admin user.

    Non-authenticated users are redirected to /login.
    Non-admins receive HTTP 403.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return current_user
