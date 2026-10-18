"""Password hashing regression tests for current and legacy accounts."""

import hashlib

from middleware.auth_middleware import (
    hash_password,
    password_needs_rehash,
    verify_password,
)


def test_new_passwords_use_salted_scrypt_hashes():
    first = hash_password("CorrectHorseBatteryStaple!")
    second = hash_password("CorrectHorseBatteryStaple!")

    assert first.startswith("scrypt:")
    assert first != second
    assert verify_password("CorrectHorseBatteryStaple!", first)
    assert not verify_password("wrong-password", first)
    assert not password_needs_rehash(first)


def test_legacy_sha256_passwords_remain_valid_for_migration():
    legacy = hashlib.sha256(b"Plant@Manager2024").hexdigest()

    assert password_needs_rehash(legacy)
    assert verify_password("Plant@Manager2024", legacy)
    assert not verify_password("wrong-password", legacy)


def test_invalid_hash_is_rejected_safely():
    assert not verify_password("password", "")
    assert not verify_password("password", "not-a-valid-password-hash")
