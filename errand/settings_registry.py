import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Setting

# Registry: key -> {env_var, sensitive, default}
SETTINGS_REGISTRY = {
    "system_prompt": {"env_var": None, "sensitive": False, "default": ""},
    "llm_model": {"env_var": None, "sensitive": False, "default": "claude-haiku-4-5-20251001"},
    "task_processing_model": {"env_var": None, "sensitive": False, "default": "claude-sonnet-4-5-20250929"},
    "transcription_model": {"env_var": None, "sensitive": False, "default": ""},
    "task_runner_log_level": {"env_var": None, "sensitive": False, "default": "INFO"},
    "timezone": {"env_var": None, "sensitive": False, "default": "UTC"},
    "archive_after_days": {"env_var": None, "sensitive": False, "default": 3},
    "mcp_servers": {"env_var": None, "sensitive": False, "default": None},
    "mcp_api_key": {"env_var": None, "sensitive": True, "default": None},
    "ssh_public_key": {"env_var": None, "sensitive": False, "default": None},
    "git_ssh_hosts": {"env_var": None, "sensitive": False, "default": ["github.com", "bitbucket.org"]},
    "skills_git_repo": {"env_var": None, "sensitive": False, "default": None},
    "openai_base_url": {"env_var": "OPENAI_BASE_URL", "sensitive": False, "default": ""},
    "openai_api_key": {"env_var": "OPENAI_API_KEY", "sensitive": True, "default": ""},
    "oidc_discovery_url": {"env_var": "OIDC_DISCOVERY_URL", "sensitive": False, "default": ""},
    "oidc_client_id": {"env_var": "OIDC_CLIENT_ID", "sensitive": False, "default": ""},
    "oidc_client_secret": {"env_var": "OIDC_CLIENT_SECRET", "sensitive": True, "default": ""},
    "oidc_roles_claim": {"env_var": "OIDC_ROLES_CLAIM", "sensitive": False, "default": "resource_access.errand.roles"},
    "litellm_mcp_servers": {"env_var": None, "sensitive": False, "default": []},
    "llm_timeout": {"env_var": None, "sensitive": False, "default": 30},
    "cloud_service_url": {"env_var": None, "sensitive": False, "default": "https://service.errand.cloud"},
    "cloud_endpoints": {"env_var": None, "sensitive": False, "default": []},
}

# Keys excluded from API responses
EXCLUDED_KEYS = {"ssh_private_key", "jwt_signing_secret"}


def mask_sensitive_value(value: str) -> str:
    """Mask a sensitive value: show first 4 chars + ****"""
    if not value or len(str(value)) <= 4:
        return "****"
    return str(value)[:4] + "****"


async def resolve_settings(session: AsyncSession) -> dict:
    """Resolve all settings with metadata: {key: {value, source, sensitive, readonly}}"""
    # Load all DB settings
    result = await session.execute(select(Setting))
    db_settings = {s.key: s.value for s in result.scalars().all()}

    resolved = {}
    for key, meta in SETTINGS_REGISTRY.items():
        if key in EXCLUDED_KEYS:
            continue

        env_var = meta["env_var"]
        sensitive = meta["sensitive"]
        default = meta["default"]

        # Resolution order: env var → DB → default
        env_value = os.environ.get(env_var) if env_var else None

        if env_value is not None and env_value != "":
            value = env_value
            if sensitive:
                value = mask_sensitive_value(value)
            resolved[key] = {
                "value": value,
                "source": "env",
                "sensitive": sensitive,
                "readonly": True,
            }
        elif key in db_settings:
            resolved[key] = {
                "value": db_settings[key],
                "source": "database",
                "sensitive": sensitive,
                "readonly": False,
            }
        else:
            resolved[key] = {
                "value": default,
                "source": "default",
                "sensitive": sensitive,
                "readonly": False,
            }

    return resolved
