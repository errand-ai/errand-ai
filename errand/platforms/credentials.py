import json
import os

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import PlatformCredential


def _get_key() -> bytes:
    key = os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY environment variable is not set")
    return key.encode()


def encrypt(data: dict) -> str:
    f = Fernet(_get_key())
    plaintext = json.dumps(data).encode()
    return f.encrypt(plaintext).decode()


def decrypt(ciphertext: str) -> dict:
    f = Fernet(_get_key())
    plaintext = f.decrypt(ciphertext.encode())
    return json.loads(plaintext)


async def load_credentials(platform_id: str, session: AsyncSession) -> dict | None:
    result = await session.execute(
        select(PlatformCredential).where(PlatformCredential.platform_id == platform_id)
    )
    cred = result.scalar_one_or_none()
    if cred is None:
        return None
    return decrypt(cred.encrypted_data)
