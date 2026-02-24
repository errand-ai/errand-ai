import logging
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from passlib.hash import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_session
from models import LocalUser, Setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/local", tags=["local-auth"])


async def _get_jwt_secret(session: AsyncSession) -> str:
    result = await session.execute(
        select(Setting).where(Setting.key == "jwt_signing_secret")
    )
    setting = result.scalar_one_or_none()
    if not setting or not setting.value:
        raise HTTPException(status_code=500, detail="JWT signing secret not configured")
    return str(setting.value)


def _mint_local_jwt(username: str, role: str, secret: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": username,
        "email": f"{username}@local",
        "_roles": [role],
        "iss": "errand-local",
        "iat": now,
        "exp": now + timedelta(hours=24),
    }
    return jwt.encode(claims, secret, algorithm="HS256")


async def _require_local_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Extract and validate a local JWT from the Authorization header."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization token")
    token_str = auth_header[7:]

    secret = await _get_jwt_secret(session)
    try:
        claims = jwt.decode(
            token_str, secret, algorithms=["HS256"], issuer="errand-local"
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return claims


@router.post("/login")
async def local_login(body: dict, session: AsyncSession = Depends(get_session)):
    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not username or not password:
        raise HTTPException(status_code=422, detail="Username and password required")

    result = await session.execute(
        select(LocalUser).where(LocalUser.username == username)
    )
    user = result.scalar_one_or_none()
    if user is None or not bcrypt.verify(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    secret = await _get_jwt_secret(session)
    token = _mint_local_jwt(username, user.role, secret)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/logout")
async def local_logout():
    return RedirectResponse(url="/", status_code=302)


@router.post("/change-password")
async def change_password(
    body: dict,
    claims: dict = Depends(_require_local_user),
    session: AsyncSession = Depends(get_session),
):
    current_password = body.get("current_password", "")
    new_password = body.get("new_password", "")

    if not current_password or not new_password:
        raise HTTPException(
            status_code=422, detail="Current password and new password required"
        )

    username = claims.get("sub", "")
    result = await session.execute(
        select(LocalUser).where(LocalUser.username == username)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not bcrypt.verify(current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    user.password_hash = bcrypt.hash(new_password)
    await session.commit()
    return {"ok": True}
