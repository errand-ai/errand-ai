"""Tests for EmailPlatform: info() and verify_credentials()."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from platforms.base import PlatformCapability, PlatformInfo
from platforms.email import EmailPlatform


class TestEmailPlatformInfo:
    def test_info_returns_correct_platform_info(self):
        platform = EmailPlatform()
        info = platform.info()

        assert isinstance(info, PlatformInfo)
        assert info.id == "email"
        assert info.label == "Email"
        assert info.capabilities == {PlatformCapability.EMAIL}

    def test_info_has_ten_credential_fields(self):
        platform = EmailPlatform()
        info = platform.info()

        assert len(info.credential_schema) == 10

    def test_info_credential_keys(self):
        platform = EmailPlatform()
        info = platform.info()

        keys = [f["key"] for f in info.credential_schema]
        assert keys == [
            "imap_host", "imap_port", "smtp_host", "smtp_port",
            "security", "username", "password", "email_profile",
            "poll_interval", "authorized_recipients",
        ]

    def test_info_security_field_has_options(self):
        platform = EmailPlatform()
        info = platform.info()

        security_field = next(f for f in info.credential_schema if f["key"] == "security")
        assert security_field["type"] == "select"
        values = [o["value"] for o in security_field["options"]]
        assert "ssl" in values
        assert "starttls" in values

    def test_info_email_profile_is_profile_select(self):
        platform = EmailPlatform()
        info = platform.info()

        profile_field = next(f for f in info.credential_schema if f["key"] == "email_profile")
        assert profile_field["type"] == "profile_select"
        assert profile_field["required"] is True


class TestEmailPlatformVerifyCredentials:
    @pytest.fixture
    def credentials(self):
        return {
            "imap_host": "imap.example.com",
            "imap_port": "993",
            "smtp_host": "smtp.example.com",
            "smtp_port": "465",
            "security": "ssl",
            "username": "user@example.com",
            "password": "secret",
        }

    @pytest.mark.asyncio
    async def test_verify_credentials_success(self, credentials):
        platform = EmailPlatform()

        mock_imap = AsyncMock()
        mock_smtp = AsyncMock()

        with patch("platforms.email.aioimaplib") as mock_aioimaplib, \
             patch("platforms.email.aiosmtplib") as mock_aiosmtplib:

            mock_aioimaplib.IMAP4_SSL.return_value = mock_imap
            mock_aiosmtplib.SMTP.return_value = mock_smtp

            result = await platform.verify_credentials(credentials)

        assert result is True
        mock_imap.wait_hello_from_server.assert_awaited_once()
        mock_imap.login.assert_awaited_once_with("user@example.com", "secret")
        mock_imap.select.assert_awaited_once_with("INBOX")
        mock_imap.logout.assert_awaited_once()

        mock_smtp.connect.assert_awaited_once()
        mock_smtp.login.assert_awaited_once_with("user@example.com", "secret")
        mock_smtp.quit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_verify_credentials_starttls(self, credentials):
        credentials["security"] = "starttls"
        credentials["imap_port"] = "143"
        credentials["smtp_port"] = "587"
        platform = EmailPlatform()

        mock_imap = AsyncMock()
        mock_smtp = AsyncMock()

        with patch("platforms.email.aioimaplib") as mock_aioimaplib, \
             patch("platforms.email.aiosmtplib") as mock_aiosmtplib:

            mock_aioimaplib.IMAP4.return_value = mock_imap
            mock_aiosmtplib.SMTP.return_value = mock_smtp

            result = await platform.verify_credentials(credentials)

        assert result is True
        mock_aioimaplib.IMAP4.assert_called_once_with(host="imap.example.com", port=143)
        mock_imap.starttls.assert_awaited_once()
        mock_aiosmtplib.SMTP.assert_called_once_with(hostname="smtp.example.com", port=587, use_tls=False)
        mock_smtp.starttls.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_verify_credentials_imap_failure(self, credentials):
        platform = EmailPlatform()

        mock_imap = AsyncMock()
        mock_imap.wait_hello_from_server.side_effect = Exception("Connection refused")

        with patch("platforms.email.aioimaplib") as mock_aioimaplib:
            mock_aioimaplib.IMAP4_SSL.return_value = mock_imap

            result = await platform.verify_credentials(credentials)

        assert result is False

    @pytest.mark.asyncio
    async def test_verify_credentials_smtp_failure(self, credentials):
        platform = EmailPlatform()

        mock_imap = AsyncMock()
        mock_smtp = AsyncMock()
        mock_smtp.connect.side_effect = Exception("SMTP connection refused")

        with patch("platforms.email.aioimaplib") as mock_aioimaplib, \
             patch("platforms.email.aiosmtplib") as mock_aiosmtplib:

            mock_aioimaplib.IMAP4_SSL.return_value = mock_imap
            mock_aiosmtplib.SMTP.return_value = mock_smtp

            result = await platform.verify_credentials(credentials)

        assert result is False
