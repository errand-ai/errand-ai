"""Webhook trigger CRUD API routes."""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.exc import IntegrityError

from database import get_session
from models import WebhookTrigger
from platforms.credentials import encrypt as encrypt_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhook-triggers", tags=["webhook-triggers"])

VALID_FILTER_KEYS = {"event_types", "issue_types", "labels", "projects"}
VALID_ACTION_KEYS = {"assign_to", "add_comment", "add_label", "transition_on_complete", "comment_output"}
ACTION_TYPES = {
    "assign_to": str,
    "add_comment": bool,
    "add_label": str,
    "transition_on_complete": str,
    "comment_output": bool,
}


async def _require_admin(request: Request):
    """Auth dependency — late import to avoid circular import with main.py."""
    from main import require_admin
    from fastapi.security import HTTPBearer
    security = HTTPBearer(auto_error=True)
    credentials = await security(request)
    return await require_admin(request, credentials)


def _parse_uuid(value: str, label: str = "ID") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {label}: {value}")


def _validate_filters(filters: dict) -> None:
    unknown = set(filters.keys()) - VALID_FILTER_KEYS
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown filter key(s): {', '.join(sorted(unknown))}")
    for key, val in filters.items():
        if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
            raise HTTPException(status_code=422, detail=f"Filter '{key}' must be an array of strings")


def _validate_actions(actions: dict) -> None:
    unknown = set(actions.keys()) - VALID_ACTION_KEYS
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown action key(s): {', '.join(sorted(unknown))}")
    for key, val in actions.items():
        expected = ACTION_TYPES.get(key)
        if expected and not isinstance(val, expected):
            raise HTTPException(status_code=422, detail=f"Action '{key}' must be a {expected.__name__}")


class TriggerCreate(BaseModel):
    name: str
    source: str
    enabled: bool = True
    profile_id: Optional[str] = None
    filters: dict = Field(default_factory=dict)
    actions: dict = Field(default_factory=dict)
    task_prompt: Optional[str] = None
    webhook_secret: Optional[str] = None


class TriggerUpdate(BaseModel):
    name: Optional[str] = None
    source: Optional[str] = None
    enabled: Optional[bool] = None
    profile_id: Optional[str] = None
    filters: Optional[dict] = None
    actions: Optional[dict] = None
    task_prompt: Optional[str] = None
    webhook_secret: Optional[str] = None


def _trigger_response(t: WebhookTrigger) -> dict:
    return {
        "id": str(t.id),
        "name": t.name,
        "source": t.source,
        "enabled": t.enabled,
        "profile_id": str(t.profile_id) if t.profile_id else None,
        "filters": t.filters or {},
        "actions": t.actions or {},
        "task_prompt": t.task_prompt,
        "has_secret": t.webhook_secret is not None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@router.get("")
async def list_triggers(
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    result = await session.execute(select(WebhookTrigger).order_by(WebhookTrigger.created_at))
    triggers = result.scalars().all()
    return [_trigger_response(t) for t in triggers]


@router.get("/{trigger_id}")
async def get_trigger(
    trigger_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    result = await session.execute(
        select(WebhookTrigger).where(WebhookTrigger.id == _parse_uuid(trigger_id, "trigger ID"))
    )
    trigger = result.scalar_one_or_none()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    return _trigger_response(trigger)


@router.post("", status_code=201)
async def create_trigger(
    body: TriggerCreate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    _validate_filters(body.filters)
    _validate_actions(body.actions)

    trigger = WebhookTrigger(
        name=body.name,
        source=body.source,
        enabled=body.enabled,
        profile_id=_parse_uuid(body.profile_id, "profile_id") if body.profile_id else None,
        filters=body.filters,
        actions=body.actions,
        task_prompt=body.task_prompt,
        webhook_secret=encrypt_secret({"secret": body.webhook_secret}) if body.webhook_secret else None,
    )
    session.add(trigger)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A trigger with this name already exists")
    await session.refresh(trigger)

    # Register with cloud if connected and secret is set
    if body.webhook_secret:
        try:
            from cloud_endpoints import try_register_trigger_endpoint
            await try_register_trigger_endpoint(
                str(trigger.id), body.source, body.webhook_secret, body.name, session,
            )
        except Exception:
            logger.warning("Cloud registration failed for trigger %s", trigger.id, exc_info=True)

    return _trigger_response(trigger)


@router.put("/{trigger_id}")
async def update_trigger(
    trigger_id: str,
    body: TriggerUpdate,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    result = await session.execute(
        select(WebhookTrigger).where(WebhookTrigger.id == _parse_uuid(trigger_id, "trigger ID"))
    )
    trigger = result.scalar_one_or_none()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    if body.filters is not None:
        _validate_filters(body.filters)
    if body.actions is not None:
        _validate_actions(body.actions)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "webhook_secret":
            setattr(trigger, field, encrypt_secret({"secret": value}) if value else None)
        elif field == "profile_id":
            setattr(trigger, field, _parse_uuid(value, "profile_id") if value else None)
        else:
            setattr(trigger, field, value)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="A trigger with this name already exists")
    await session.refresh(trigger)

    # Re-register with cloud if secret was updated
    if "webhook_secret" in update_data and update_data["webhook_secret"]:
        try:
            from cloud_endpoints import try_register_trigger_endpoint
            await try_register_trigger_endpoint(
                str(trigger.id), trigger.source, update_data["webhook_secret"], trigger.name, session,
            )
        except Exception:
            logger.warning("Cloud re-registration failed for trigger %s", trigger.id, exc_info=True)

    return _trigger_response(trigger)


@router.delete("/{trigger_id}", status_code=204)
async def delete_trigger(
    trigger_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    result = await session.execute(
        select(WebhookTrigger).where(WebhookTrigger.id == _parse_uuid(trigger_id, "trigger ID"))
    )
    trigger = result.scalar_one_or_none()
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    # Deregister from cloud before deleting
    try:
        from cloud_endpoints import try_deregister_trigger_endpoint
        await try_deregister_trigger_endpoint(str(trigger.id), trigger.source, session)
    except Exception:
        logger.warning("Cloud deregistration failed for trigger %s", trigger.id, exc_info=True)

    await session.delete(trigger)
    await session.commit()
