"""Thin MCP client wrapper for the Errand endpoint.

The driver is a *pure MCP client*: every interaction with Errand goes through
tool calls here — no DB, Kubernetes, or SSH. Errand's MCP tools return JSON
strings, which this wrapper parses into Python objects.

The public methods (``new_task``, ``task_status``, ``task_output``,
``task_logs``, ``list_tasks``, ``clone_task_profile``, ``delete_task_profile``,
``search_tasks``, ``start_eval_run``, ``record_eval_result``,
``finish_eval_run``, ``get_eval_run``) define the surface the runner/retro use;
tests substitute a fake object exposing the same methods, so the orchestration
logic is exercised without a live server.
"""

from __future__ import annotations

import json

# The `mcp` client library is only needed for the live wrapper; importing lazily
# keeps the module (and the fake-client-based tests) usable without it installed.
try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
except Exception:  # noqa: BLE001
    ClientSession = None
    streamablehttp_client = None


class MCPError(RuntimeError):
    """An MCP tool returned an error payload."""


def _parse_tool_text(text: str):
    """Parse a tool's returned text as JSON when possible, else return raw text."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text


class ErrandMCPClient:
    """Live client over MCP streamable HTTP with Bearer (mcp_api_key) auth.

    Opens a fresh session per call — the driver is low-frequency (one in-flight
    task) so per-call connect overhead is irrelevant and statelessness is simpler
    and more robust than holding a long-lived session across hour-long polls.
    """

    def __init__(self, mcp_url: str, api_key: str, retries: int = 3):
        if streamablehttp_client is None:
            raise RuntimeError("the 'mcp' package is required for the live client (pip install mcp)")
        self._url = mcp_url
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._retries = retries

    async def _call(self, tool: str, arguments: dict | None = None):
        import asyncio

        last_exc: Exception | None = None
        for attempt in range(1, self._retries + 1):
            try:
                async with streamablehttp_client(self._url, headers=self._headers) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool, arguments or {})
                        texts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
                        return _parse_tool_text("".join(texts))
            except Exception as exc:  # noqa: BLE001 — retry transient transport errors
                last_exc = exc
                if attempt < self._retries:
                    await asyncio.sleep(min(2 ** attempt, 10))
        raise MCPError(f"tool '{tool}' failed after {self._retries} attempts: {last_exc}")

    # --- task lifecycle ---
    async def new_task(self, description, profile=None, title=None):
        return await self._call("new_task", {"description": description, "profile": profile, "title": title})

    async def task_status(self, task_id, fmt="json"):
        return await self._call("task_status", {"task_id": task_id, "format": fmt})

    async def task_output(self, task_id):
        return await self._call("task_output", {"task_id": task_id})

    async def task_logs(self, task_id):
        return await self._call("task_logs", {"task_id": task_id})

    async def list_tasks(self, status=None):
        return await self._call("list_tasks", {"status": status})

    # --- eval framework tools ---
    async def clone_task_profile(self, source_profile, new_name, model=None, llm_timeout=None, max_turns=None):
        return await self._call("clone_task_profile", {
            "source_profile": source_profile, "new_name": new_name,
            "model": model, "llm_timeout": llm_timeout, "max_turns": max_turns,
        })

    async def delete_task_profile(self, name):
        return await self._call("delete_task_profile", {"name": name})

    async def search_tasks(self, **filters):
        return await self._call("search_tasks", filters)

    async def start_eval_run(self, mode, corpus_version, judge_model, driver_host=None, notes=None):
        return await self._call("start_eval_run", {
            "mode": mode, "corpus_version": corpus_version, "judge_model": judge_model,
            "driver_host": driver_host, "notes": notes,
        })

    async def record_eval_result(self, **fields):
        return await self._call("record_eval_result", fields)

    async def finish_eval_run(self, run_id, notes=None):
        return await self._call("finish_eval_run", {"run_id": run_id, "notes": notes})

    async def get_eval_run(self, run_id):
        return await self._call("get_eval_run", {"run_id": run_id})
