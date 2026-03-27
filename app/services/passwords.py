import hashlib

from passlib.context import CryptContext

# bcrypt only accepts 72 bytes; we hash UTF-8 passwords with SHA-256 first (hex = 64 chars, always safe).
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _sha256_hex(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def hash_password(plain: str) -> str:
    return _pwd.hash(_sha256_hex(plain))


def verify_password(plain: str, password_hash: str) -> bool:
    if _pwd.verify(_sha256_hex(plain), password_hash):
        return True
    # Legacy: hashes created before pre-hashing (bcrypt of raw password)
    try:
        return bool(_pwd.verify(plain, password_hash))
    except ValueError:
        return False
