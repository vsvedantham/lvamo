"""Encryption for credentials users give Applaut (engine 3's Neon URL and R2
keys). Fernet tokens, keyed by APPLAUT_CREDENTIALS_KEY; a MultiFernet so a
new key can be put first while the old one still decrypts (then re-encrypt
with `rotate`)."""
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import settings


class CredentialsUnavailable(RuntimeError):
    """No key configured, or a stored value can't be decrypted with it."""


def _fernet() -> MultiFernet:
    keys = [k.strip() for k in (settings.applaut_credentials_key or "").split(",") if k.strip()]
    if not keys:
        raise CredentialsUnavailable("APPLAUT_CREDENTIALS_KEY is not set")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except ValueError as exc:
        raise CredentialsUnavailable("APPLAUT_CREDENTIALS_KEY is not a valid Fernet key") from exc


def is_configured() -> bool:
    try:
        _fernet()
    except CredentialsUnavailable:
        return False
    return True


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise CredentialsUnavailable("stored credentials can't be decrypted with the current key") from exc


def rotate(token: str) -> str:
    """Re-encrypt a token with the first (newest) key."""
    return _fernet().rotate(token.encode()).decode()
