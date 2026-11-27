import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_ALGORITHM = "HS256"
_ISSUER = "sme-cyber-monitor"


def new_opaque_token(nbytes: int = 32) -> str:
    """A random URL-safe token for refresh tokens, invitations and password resets."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Opaque tokens are high-entropy, so a fast hash is enough to store them safely."""
    return hashlib.sha256(token.encode()).hexdigest()


def _encode(claims: dict[str, Any], ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {**claims, "iat": now, "nbf": now, "exp": now + ttl, "iss": _ISSUER}
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict[str, Any] | None:
    try:
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.PyJWTError:
        return None
    if claims.get("typ") != expected_type:
        return None
    return claims


def create_access_token(user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return _encode(
        {"sub": str(user_id), "sid": str(session_id), "typ": "access"},
        timedelta(minutes=settings.access_token_ttl_minutes),
    )


def create_mfa_token(user_id: uuid.UUID) -> str:
    """Proves the password step succeeded; only usable at the MFA verification endpoint."""
    return _encode(
        {"sub": str(user_id), "typ": "mfa", "jti": secrets.token_hex(8)},
        timedelta(minutes=settings.mfa_token_ttl_minutes),
    )


def create_email_token(user_id: uuid.UUID, email: str) -> str:
    """Proves control of an email address. Bound to the address, so changing it voids the link."""
    return _encode(
        {"sub": str(user_id), "typ": "verify_email", "email": email.lower()},
        timedelta(hours=48),
    )


_fernet = Fernet(settings.fernet_key)


def encrypt_secret(value: str) -> str:
    return _fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str | None:
    try:
        return _fernet.decrypt(value.encode()).decode()
    except InvalidToken:
        return None
