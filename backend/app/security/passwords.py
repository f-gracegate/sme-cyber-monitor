from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# Argon2id with OWASP-recommended baseline parameters (19 MiB, t=2, p=1).
_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

# A dummy hash used to keep response timing similar when a user does not exist.
_DUMMY_HASH = _hasher.hash("timing-equaliser-not-a-real-password")

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

_COMMON_PASSWORDS = {
    "password",
    "password1",
    "password123",
    "passw0rd",
    "123456789012",
    "qwertyuiop12",
    "letmein12345",
    "welcome12345",
    "administrator",
    "changeme1234",
    "iloveyou1234",
    "ghana1234567",
    "accra1234567",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and bool(password_hash)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_policy_errors(password: str, *, email: str = "", username: str = "") -> list[str]:
    """Return human-readable reasons a new password is unacceptable (empty if acceptable)."""
    errors: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        errors.append(f"Use at most {MAX_PASSWORD_LENGTH} characters.")
    lowered = password.lower()
    if lowered in _COMMON_PASSWORDS or len(set(password)) < 5:
        errors.append("This password is too common or too simple.")
    local_part = email.split("@")[0].lower() if email else ""
    if (local_part and len(local_part) >= 4 and local_part in lowered) or (
        username and len(username) >= 4 and username.lower() in lowered
    ):
        errors.append("Do not include your email address or username.")
    return errors
