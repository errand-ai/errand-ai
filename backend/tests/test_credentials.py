"""Tests for credential encryption/decryption (Task 4.3)."""
import os

import pytest
from cryptography.fernet import Fernet

from platforms.credentials import encrypt, decrypt, _get_key


def test_encrypt_decrypt_round_trip(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key)

    data = {"api_key": "abc123", "api_secret": "xyz789"}
    ciphertext = encrypt(data)
    assert isinstance(ciphertext, str)
    assert ciphertext != str(data)

    result = decrypt(ciphertext)
    assert result == data


def test_encrypt_decrypt_empty_dict(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key)

    data = {}
    ciphertext = encrypt(data)
    assert decrypt(ciphertext) == {}


def test_get_key_missing_raises(monkeypatch):
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_KEY"):
        _get_key()


def test_decrypt_wrong_key_raises(monkeypatch):
    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key1)
    ciphertext = encrypt({"secret": "value"})

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key2)
    with pytest.raises(Exception):
        decrypt(ciphertext)


def test_encrypt_produces_different_ciphertext_each_call(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", key)

    data = {"key": "value"}
    ct1 = encrypt(data)
    ct2 = encrypt(data)
    assert ct1 != ct2  # Fernet includes a timestamp, so ciphertext differs
    assert decrypt(ct1) == decrypt(ct2) == data
