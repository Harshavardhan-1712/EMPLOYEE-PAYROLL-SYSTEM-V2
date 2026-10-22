from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_ph = PasswordHasher()
# Verified against when the username is unknown, so response time does not reveal which usernames exist.
_DUMMY_HASH = _ph.hash("not-a-real-password")
MIN_PASSWORD_LENGTH = 12


def validate_password_strength(pw: str) -> None:
    if len(pw) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def hash_password(pw: str) -> str:
    validate_password_strength(pw)
    return _ph.hash(pw)


def verify_password(pw: str, stored_hash: str | None) -> bool:
    try:
        return _ph.verify(stored_hash or _DUMMY_HASH, pw) and stored_hash is not None
    except (VerificationError, InvalidHashError):
        return False
