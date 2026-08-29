## 1. Branch and version

- [ ] 1.1 Confirm `update-vulnerable-dependencies` and `address-security-review-findings` are both merged. This change touches `errand/mcp_server.py`, which the security-review change also rewrites; landing second avoids rebasing the more delicate work
- [ ] 1.2 Create branch `migrate-mcp-sdk-v2` from an up-to-date `main`
- [ ] 1.3 Bump `VERSION` — minor. No intended change for MCP clients, but the SDK under the endpoint changes major and tool error text becomes less specific

## 2. Pin the 421 before touching anything

The failure this change most plausibly ships is DNS rebinding protection silently switching back on: `streamable_http_app()` defaults to `host="127.0.0.1"` and auto-enables it when no `transport_security` is passed, and the app starts healthy while every request fails. CLAUDE.md records this exact `421` from the last time. Write the test while the code still passes it.

- [ ] 2.1 Write a test that sends an authenticated MCP request to `/mcp` with a `Host` header naming a real hostname (both with and without a port) and asserts the request is processed and the response is **not** `421 Invalid Host header`
- [ ] 2.2 Confirm it passes on the current v1 code. A test that only ever ran green after the change proves nothing about whether the parameter landed
- [ ] 2.3 Confirm it fails if `transport_security` is removed. If it passes either way it is not testing what it claims to

## 3. Resolve the `_tool_manager` question first

`errand/mcp_server.py:70` wraps `mcp._tool_manager.call_tool` to log tool invocations. Private API. The migration guide is thorough about private moves — it names `_mcp_server` → `_lowlevel_server` — and says nothing about `_tool_manager`. Silence is not a guarantee, and the answer decides how large section 4 is.

- [ ] 3.1 Install mcp 2.1.1 in a scratch venv and check whether `MCPServer` still exposes `_tool_manager` with a `call_tool` attribute
- [ ] 3.2 If it survives: keep the wrapper for now, and record in the code that it is private API and the supported seam is `middleware`
- [ ] 3.3 If it does not: replace the logging with the `middleware` constructor parameter (new in v2, keyword-only). This is the better end state either way — see the design open question — but it is a larger diff, so take it on evidence
- [ ] 3.4 Either way, confirm the tool-invocation logging still appears in the container log. It is the only per-tool trace there is

## 4. Migrate the server

- [ ] 4.1 `errand/mcp_server.py`: `from mcp.server.fastmcp import Context, FastMCP` → `from mcp.server.mcpserver import Context, MCPServer`. The whole subtree moved `fastmcp.*` → `mcpserver.*` with the same structure
- [ ] 4.2 Leave the other three imports alone — `mcp.server.auth.provider`, `mcp.server.auth.settings` and `mcp.server.transport_security` are all listed as unchanged in v2, and "fixing" them is how a mechanical migration introduces a bug
- [ ] 4.3 `FastMCP(...)` → `MCPServer(...)`. Keep `auth=` and `token_verifier=` on the constructor; they did not move
- [ ] 4.4 Move `stateless_http`, `json_response`, `streamable_http_path` and `transport_security` off the constructor and onto `streamable_http_app()` in `create_mcp_app()` (`mcp_server.py:2199`). v2 does not accept them on the constructor
- [ ] 4.5 Keep only `"Errand"` positional. v2 inserted `title` and `description` before `instructions` in the positional order — a v1 call passing `instructions` positionally still runs, but the text silently lands in `title` and `instructions` stops being sent to clients. errand passes only the name, so this is a trap to avoid re-introducing, not one to fix
- [ ] 4.6 Confirm `mcp.session_manager.run()` in `main.py:372` still works unchanged. It is the same public property, and it still exists only after `streamable_http_app()` has been called — so the app must still be built at module level and the manager touched only inside the lifespan
- [ ] 4.7 Confirm nothing calls `MCPServer.get_context()` — it was removed in v2. errand injects `ctx: Context | None = None` into handlers instead, which is the supported pattern
- [ ] 4.8 Confirm all 35 `@mcp.tool()` handlers are untouched. The guide states the decorators take the same arguments and handler signatures as v1; if a handler needed changing, something else is wrong

## 5. Requirement

- [ ] 5.1 `errand/requirements.txt`: `mcp[http]>=1.23.2,<2` → `mcp>=2.1.1,<3`
- [ ] 5.2 Drop the `[http]` extra — v2 does not publish it (`provides_extra: ['cli', 'rich']` on 2.1.1); HTTP support is no longer optional
- [ ] 5.3 Keep an upper bound. An unbounded major is what cost a day on 2026-07-28; the bound is the lesson, not the version
- [ ] 5.4 Note that mcp 2.x pulls `httpx2>=2.5.0` and no longer uses `httpx`. errand keeps its own `httpx==0.28.1` and both will be in the image. Expected, not a conflict — but confirm the image builds and nothing imports the wrong one
- [ ] 5.5 Decide whether to raise `pydantic>=2.11.0` to `>=2.12.0`, which mcp 2.x requires. pip resolves it upward regardless; this is about whether the file states its real minimum

## 6. Verify

- [ ] 6.1 The `Host`-header test from section 2 passes
- [ ] 6.2 Backend suite green: `DATABASE_URL="sqlite+aiosqlite:///:memory:" errand/.venv/bin/python -m pytest errand/tests/ -v`
- [ ] 6.3 `tools/list` against the migrated server returns the same 35 tool names, with the same parameters, as before the migration. Capture both and diff them — this is the requirement the change exists to preserve
- [ ] 6.4 **Run a real task end to end.** The task-runner is an mcp **v1** client (`agents.mcp.MCPServerStreamableHttp`, constrained `mcp<2,>=1.19.0` by `openai-agents`) talking to a v2 server. Cross-version compatibility is what the protocol is for, and it is still an assumption until a task actually completes
- [ ] 6.5 Check whether the task-runner's auto-enable-on-error tool recovery matches on tool error text. v2.1.0 logs handler exceptions server-side and returns clients a generic `"Error executing tool <name>"`; if anything downstream parses the old message, it stops working silently
- [ ] 6.6 Confirm the eval driver still connects. `evals/` stays on mcp v1 and uses `streamablehttp_client`, removed in v2 — it is unaffected as long as it stays on v1, which is the point of checking

## 7. Spec

- [ ] 7.1 Apply the `mcp-server-endpoint` delta. Note what is being corrected: the requirement has said `MCPServer` from `mcp.server.mcpserver` since **2026-02-13**, five months before mcp 2.0.0 introduced that module, while the code used `FastMCP` throughout. It also places `streamable_http_path="/"` on the constructor, where v2 does not accept it. Both are fixed; the second only becomes true after section 4
- [ ] 7.2 `validate-specs` green in CI

## 8. Ship

- [ ] 8.1 Commit, push, open a PR
- [ ] 8.2 CI green
- [ ] 8.3 Deploy to Kubernetes and confirm MCP works **against the real hostname through the ingress**, not a localhost smoke test. The `421` this change guards against is invisible to a loopback check
- [ ] 8.4 Confirm a task submitted through MCP runs to completion on the deployed build
- [ ] 8.5 Merge, delete branch

## 9. Follow-ups, not done here

- [ ] 9.1 `task-runner/requirements.txt` declares `mcp>=1.0.0` with no upper bound, and escaped the 2026-07-28 breakage only because `openai-agents` declares `mcp<2,>=1.19.0` on its behalf. Same defect, still live, protected by a third party. One line, and it should not wait for this change
- [ ] 9.2 Move the tool-call logging to `middleware` if section 3 kept the private wrapper. It is a known future breakage
