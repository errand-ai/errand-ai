"""Driver configuration: evals/config.yaml plus command-line overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass

import yaml


@dataclass
class Config:
    mcp_url: str
    api_key_env: str
    models: list[str]
    judge_model: str
    yield_poll_interval_seconds: int = 30
    task_poll_interval_seconds: int = 15
    digest_max_chars: int = 12000

    def api_key(self) -> str:
        """Resolve the MCP API key from the configured environment variable."""
        key = os.environ.get(self.api_key_env, "").strip()
        if not key:
            raise RuntimeError(
                f"MCP API key env var '{self.api_key_env}' is unset — export it before running the driver"
            )
        return key


def load_config(path: str, overrides: dict | None = None) -> Config:
    """Load config.yaml and apply CLI overrides (only non-None override values)."""
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    errand = raw.get("errand", {})
    cfg = Config(
        mcp_url=errand.get("mcp_url", ""),
        api_key_env=errand.get("api_key_env", "ERRAND_MCP_API_KEY"),
        models=list(raw.get("models", [])),
        judge_model=raw.get("judge_model", "claude-opus-4-8"),
        yield_poll_interval_seconds=int(raw.get("yield_poll_interval_seconds", 30)),
        task_poll_interval_seconds=int(raw.get("task_poll_interval_seconds", 15)),
        digest_max_chars=int(raw.get("digest_max_chars", 12000)),
    )
    for k, v in (overrides or {}).items():
        if v is not None and hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg
