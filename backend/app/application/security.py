import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.config import settings

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(user_id: UUID, role: str) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=settings.jwt_access_minutes)
    return jwt.encode(
        {"sub": str(user_id), "role": role, "exp": expires, "jti": secrets.token_urlsafe(16)},
        settings.jwt_secret_key,
        algorithm=ALGORITHM,
    )


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def refresh_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.jwt_refresh_days)


def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)
