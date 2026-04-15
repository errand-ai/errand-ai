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
from models import TaskProfile, WebhookTrigger
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

GITHUB_VALID_FILTER_KEYS = {"project_node_id", "trigger_column", "content_types"}
GITHUB_REQUIRED_FILTER_KEYS = {"project_node_id", "trigger_column"}
GITHUB_VALID_CONTENT_TYPES = {"Issue", "PullRequest", "DraftIssue"}
GITHUB_VALID_ACTION_KEYS = {
    "add_comment", "comment_output", "column_on_running", "column_on_complete",
    "copilot_review", "review_profile_id", "project_field_id", "column_options",
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


def _validate_github_filters(filters: dict) -> None:
    unknown = set(filters.keys()) - GITHUB_VALID_FILTER_KEYS
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown filter key(s): {', '.join(sorted(unknown))}")
    for key in GITHUB_REQUIRED_FILTER_KEYS:
        if key not in filters:
            raise HTTPException(status_code=422, detail=f"Missing required filter key: {key}")
        if not isinstance(filters[key], str):
            raise HTTPException(status_code=422, detail=f"Filter '{key}' must be a string")
    if "content_types" in filters:
        ct = filters["content_types"]
        if not isinstance(ct, list) or not all(isinstance(v, str) for v in ct):
            raise HTTPException(status_code=422, detail="Filter 'content_types' must be an array of strings")
        invalid = set(ct) - GITHUB_VALID_CONTENT_TYPES
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid content_types: {', '.join(sorted(invalid))}. "
                       f"Valid values: {', '.join(sorted(GITHUB_VALID_CONTENT_TYPES))}",
            )


def _validate_github_actions(actions: dict) -> None:
    unknown = set(actions.keys()) - GITHUB_VALID_ACTION_KEYS
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown action key(s): {', '.join(sorted(unknown))}")
    for key in ("add_comment", "comment_output", "copilot_review"):
        if key in actions and not isinstance(actions[key], bool):
            raise HTTPException(status_code=422, detail=f"Action '{key}' must be a bool")
    for key in ("column_on_running", "column_on_complete"):
        if key in actions and not isinstance(actions[key], str):
            raise HTTPException(status_code=422, detail=f"Action '{key}' must be a str")
    if "review_profile_id" in actions:
        _parse_uuid(actions["review_profile_id"], "review_profile_id")
    if "column_options" in actions and not isinstance(actions["column_options"], dict):
        raise HTTPException(status_code=422, detail="Action 'column_options' must be a dict")
    if "project_field_id" in actions and not isinstance(actions["project_field_id"], str):
        raise HTTPException(status_code=422, detail="Action 'project_field_id' must be a str")
    # Validate column names against column_options if both are provided
    # column_options format: {"ColumnName": "option_id", ...}
    if "column_options" in actions:
        option_names = set(actions["column_options"].keys())
        for col_key in ("column_on_running", "column_on_complete"):
            col_val = actions.get(col_key)
            if col_val and col_val not in option_names:
                raise HTTPException(
                    status_code=422,
                    detail=f"Action '{col_key}' value '{col_val}' not found in column_options",
                )


async def _validate_github_review_profile(actions: dict, session: AsyncSession) -> None:
    """Check that review_profile_id references an existing TaskProfile."""
    profile_id_str = actions.get("review_profile_id")
    if not profile_id_str:
        return
    profile_uuid = _parse_uuid(profile_id_str, "review_profile_id")
    result = await session.execute(select(TaskProfile).where(TaskProfile.id == profile_uuid))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=422, detail=f"TaskProfile not found: {profile_id_str}")


async def _ensure_github_column_options(filters: dict, actions: dict, session: AsyncSession) -> dict:
    """Validate column_options are present and column names exist when column actions are configured.

    Requires the frontend to call the introspect endpoint first to populate column_options.
    Raises 422 if column actions are set without column_options/project_field_id.
    """
    has_column_actions = actions.get("column_on_running") or actions.get("column_on_complete")
    if not has_column_actions:
        return actions

    if actions.get("column_options") and actions.get("project_field_id"):
        # Already cached — validate column names exist
        opts = actions["column_options"]
        for key in ("column_on_running", "column_on_complete"):
            col_name = actions.get(key)
            if col_name and col_name not in opts:
                available = list(opts.keys())
                raise HTTPException(
                    status_code=422,
                    detail=f"Column '{col_name}' not found in project. Available: {available}",
                )
        return actions

    # Need to auto-introspect — but we need org + project_number
    # The project_node_id is in filters but we can't reverse-lookup org/number from it
    # Require column_options to be provided (via frontend introspection)
    raise HTTPException(
        status_code=422,
        detail="column_on_running or column_on_complete requires column_options. "
        "Use the project introspection endpoint first to discover column options.",
    )


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
    if body.source == "github":
        _validate_github_filters(body.filters)
        _validate_github_actions(body.actions)
        await _validate_github_review_profile(body.actions, session)
        body.actions = await _ensure_github_column_options(body.filters, body.actions, session)
    else:
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

    source = body.source if body.source is not None else trigger.source
    source_changed = body.source is not None and body.source != trigger.source
    if source == "github":
        effective_filters = body.filters if body.filters is not None else (trigger.filters or {})
        effective_actions = body.actions if body.actions is not None else (trigger.actions or {})
        if body.filters is not None or source_changed:
            _validate_github_filters(effective_filters)
        if body.actions is not None or source_changed:
            _validate_github_actions(effective_actions)
            await _validate_github_review_profile(effective_actions, session)
            body.actions = await _ensure_github_column_options(effective_filters, effective_actions, session)
    else:
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


@router.post("/github/introspect-project")
async def introspect_github_project(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(_require_admin),
):
    body = await request.json()
    org = body.get("org")
    project_number = body.get("project_number")
    if not org or not isinstance(org, str):
        raise HTTPException(status_code=400, detail="org (string) and project_number (integer) required")
    if not isinstance(project_number, int):
        raise HTTPException(status_code=400, detail="org (string) and project_number (integer) required")

    from platforms.github.client import GitHubClient, GitHubClientError

    try:
        client = await GitHubClient.from_credentials(session)
    except GitHubClientError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await client.introspect_project(org, project_number)
    except GitHubClientError as e:
        raise HTTPException(status_code=400, detail=str(e))

    status_field = None
    for field in result["fields"]:
        if field.get("type") == "SingleSelectField" and field["name"] == "Status":
            status_field = {"field_id": field["id"], "options": field["options"]}
            break

    return {
        "project_node_id": result["project_node_id"],
        "title": result["title"],
        "status_field": status_field,
    }
