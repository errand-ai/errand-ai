import logging

import aioimaplib
import aiosmtplib

from platforms.base import Platform, PlatformCapability, PlatformInfo

logger = logging.getLogger(__name__)


class EmailPlatform(Platform):
    def info(self) -> PlatformInfo:
        return PlatformInfo(
            id="email",
            label="Email",
            capabilities={PlatformCapability.EMAIL},
            credential_schema=[
                {"key": "imap_host", "label": "IMAP Server", "type": "text", "required": True},
                {"key": "imap_port", "label": "IMAP Port", "type": "text", "required": True},
                {"key": "smtp_host", "label": "SMTP Server", "type": "text", "required": True},
                {"key": "smtp_port", "label": "SMTP Port", "type": "text", "required": True},
                {
                    "key": "security",
                    "label": "Security",
                    "type": "select",
                    "options": [
                        {"label": "SSL/TLS", "value": "ssl"},
                        {"label": "STARTTLS", "value": "starttls"},
                    ],
                },
                {"key": "username", "label": "Email Address", "type": "text", "required": True},
                {"key": "password", "label": "Password / App Password", "type": "password", "required": True},
                {"key": "email_profile", "label": "Task Profile", "type": "profile_select", "required": True},
                {
                    "key": "poll_interval",
                    "label": "Poll Interval (seconds)",
                    "type": "text",
                    "required": False,
                    "help_text": "Minimum 60. Reduced when IMAP IDLE is supported.",
                },
                {
                    "key": "authorized_recipients",
                    "label": "Authorised Recipients",
                    "type": "textarea",
                    "required": False,
                    "help_text": "One email per line. Agent can only send/forward to these.",
                },
            ],
        )

    async def verify_credentials(self, credentials: dict) -> bool:
        host = credentials["imap_host"]
        port = int(credentials["imap_port"])
        username = credentials["username"]
        password = credentials["password"]
        security = credentials.get("security", "ssl")

        # Determine IMAP security from port (993=SSL, 143=STARTTLS, else follow toggle)
        imap_use_ssl = port == 993 or (port != 143 and security == "ssl")
        imap_use_starttls = not imap_use_ssl

        # Verify IMAP
        try:
            if imap_use_ssl:
                imap = aioimaplib.IMAP4_SSL(host=host, port=port)
            else:
                imap = aioimaplib.IMAP4(host=host, port=port)
            await imap.wait_hello_from_server()

            if imap_use_starttls:
                await imap.starttls()

            await imap.login(username, password)
            await imap.select("INBOX")
            await imap.logout()
        except Exception:
            logger.exception("Email IMAP credential verification failed")
            return False

        # Determine SMTP security from port (465=SSL, 587/25=STARTTLS, else follow toggle)
        smtp_host = credentials["smtp_host"]
        smtp_port = int(credentials["smtp_port"])
        smtp_use_ssl = smtp_port == 465 or (smtp_port not in (587, 25) and security == "ssl")

        # Verify SMTP
        try:
            smtp = aiosmtplib.SMTP(
                hostname=smtp_host,
                port=smtp_port,
                use_tls=smtp_use_ssl,
            )
            await smtp.connect()
            if not smtp_use_ssl:
                await smtp.starttls()
            await smtp.login(username, password)
            await smtp.quit()
        except Exception:
            logger.exception("Email SMTP credential verification failed")
            return False

        return True
