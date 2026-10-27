import pytest

from app.auth.passwords import hash_password, validate_password, verify_password


def test_scrypt_password_round_trip_uses_distinct_salts():
    first = hash_password("StrongPassword@123")
    second = hash_password("StrongPassword@123")

    assert first != second
    assert "StrongPassword@123" not in first
    assert verify_password("StrongPassword@123", first) is True
    assert verify_password("wrong", first) is False
    assert verify_password("anything", "malformed") is False


@pytest.mark.parametrize(
    "password",
    ["Short@1", "alllowercase@123", "ALLUPPERCASE@123", "NoSymbols12345", "NoDigits@Password"],
)
def test_password_policy_rejects_weak_passwords(password: str):
    with pytest.raises(ValueError, match="密码至少需要 12 位"):
        validate_password(password)
