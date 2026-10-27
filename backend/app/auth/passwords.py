from __future__ import annotations

import base64
import hashlib
import hmac
import os


_N = 16384
_R = 8
_P = 1
_DKLEN = 32
_ERROR = "密码至少需要 12 位，并包含大写字母、小写字母、数字和符号。"


def validate_password(password: str) -> None:
    if (
        len(password) < 12
        or not any(character.isupper() for character in password)
        or not any(character.islower() for character in password)
        or not any(character.isdigit() for character in password)
        or not any(not character.isalnum() for character in password)
    ):
        raise ValueError(_ERROR)


def hash_password(password: str) -> str:
    validate_password(password)
    salt = os.urandom(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN
    )
    return "$".join(
        (
            "scrypt",
            "v=1",
            f"n={_N}",
            f"r={_R}",
            f"p={_P}",
            _encode(salt),
            _encode(digest),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, version, n_value, r_value, p_value, salt_text, digest_text = (
            encoded.split("$")
        )
        if algorithm != "scrypt" or version != "v=1":
            return False
        salt = _decode(salt_text)
        expected = _decode(digest_text)
        actual = hashlib.scrypt(
            password.encode(),
            salt=salt,
            n=int(n_value.removeprefix("n=")),
            r=int(r_value.removeprefix("r=")),
            p=int(p_value.removeprefix("p=")),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
