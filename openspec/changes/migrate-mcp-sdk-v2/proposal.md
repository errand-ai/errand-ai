## Why

`errand/requirements.txt` carries `mcp[http]>=1.23.2,<2`. The `<2` is not tidiness — it is a load-bearing guard added reactively on 2026-07-28, the day mcp 2.0.0 removed `mcp.server.fastmcp` and errand's next build failed at pytest collection with zero tests run. It went in as a one-line edit inside commit `05c3791`, a PR titled *"Restore MCP server configuration UI"*, and nothing in the requirements file records why it is there.

The bound is correct and should stay until the migration is done. The SDK's own guide says so:

> **Not ready to migrate yet?** The v1.x maintenance line keeps receiving critical bug fixes and security patches... If your package depends on `mcp`, keep a `<2` upper bound until you've migrated.

Nothing since 2.0.0 changes that. Checked as of 2026-08-29:

| Version | Date | What it is |
|---|---|---|
| 2.1.0 | 2026-08-24 | Feature release |
| 2.1.1 | 2026-08-25 | *"Point imports of `mcp.server.fastmcp` at the migration guide"* |
| 2.0.1 | 2026-08-26 | *"One off backport of the FastMCP import warning for `2.0.x`, this is due to a lot of people running into this error"* |

Both of the last two exist *because* of this breakage, and neither reverses it. Upstream backported a better `ModuleNotFoundError` to the 2.0.x line because enough people hit the same wall. The migration guide is explicit: *"Importing `mcp.server.fastmcp`, or anything below it, raises `ModuleNotFoundError`."* There is no shim and no alias.

### Why do it now, when nothing is forcing it

Nothing is. v1.x still receives security patches and 1.29.1 shipped on 2026-08-24, five days before this proposal. There is no cliff.

The argument is that the work is unusually small *right now*, and that will not improve:

- **The tool surface is uniform.** All 35 `@mcp.tool()` handlers return `-> str`. No resources, no prompts, no completions, no structured output, no `CallToolResult`, no `MCPError`. The v2 guide confirms `@mcp.tool()` takes the same arguments and handler signatures as v1, so **none of the 35 tools change**.
- **Three of errand's four mcp imports do not move.** `mcp.server.auth.provider`, `mcp.server.auth.settings` and `mcp.server.transport_security` are all listed under "unchanged". Only `mcp.server.fastmcp` moves, wholesale, to `mcp.server.mcpserver` with the same structure.
- **The spec already describes v2.** `mcp-server-endpoint` has said *"The server SHALL use `MCPServer` from `mcp.server.mcpserver`"* since **2026-02-13** — five months before mcp 2.0.0 existed and named that module. The code has used `FastMCP` throughout. The requirement has been wrong for six months and happens to have guessed the name v2 later adopted.

Every month spent on v1 adds tools, and the migration cost scales with the surface. It is a handful of lines today.

## What Changes

- Move the server from `FastMCP` to `MCPServer`: `from mcp.server.mcpserver import Context, MCPServer` in `errand/mcp_server.py`.
- Move the transport keywords off the constructor. `stateless_http`, `json_response`, `streamable_http_path` and `transport_security` are no longer constructor parameters in v2; they belong on `streamable_http_app()`. `auth` and `token_verifier` stay on the constructor.
- **Pass `transport_security` explicitly to `streamable_http_app()`.** Not optional — see Impact.
- Change the requirement to `mcp>=2.1.1,<3`. **The `[http]` extra does not exist in v2** — PyPI metadata for 2.1.1 gives `provides_extra: ['cli', 'rich']`. HTTP support is no longer optional, so the extra was dropped.
- Replace the `mcp._tool_manager.call_tool` monkeypatch (`errand/mcp_server.py:70`) or verify it still holds. It is private API and the migration guide does not mention `_tool_manager` at all.
- Correct the `mcp-server-endpoint` requirement so it describes what the code actually does — including where the transport parameters now live, which the current text also gets wrong.

**Not in scope:**

- `task-runner` and `evals` stay on mcp v1. The task-runner reaches errand through `agents.mcp.MCPServerStreamableHttp` from `openai-agents`, which constrains `mcp<2,>=1.19.0` on its behalf; `evals` pins its own version. MCP is a wire protocol, so a v1 client against a v2 server is expected to work — expected, and therefore something to verify rather than assume.
- Adding the missing upper bound to `task-runner/requirements.txt` (`mcp>=1.0.0`, unbounded, protected only by `openai-agents`). Same class of defect as the one that caused the outage, still live. It belongs in this area of the code but not in this change; it should not wait for this change either.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-server-endpoint`: the "MCP server mounted at /mcp" requirement names `MCPServer` from `mcp.server.mcpserver` (which the code has never used) and places `streamable_http_path="/"` on the constructor (where v2 does not accept it). Corrected to describe the v2 arrangement accurately, and to require that `transport_security` is passed to `streamable_http_app()` rather than relied on by default.

## Impact

- **Code**: `errand/mcp_server.py` (imports, constructor, app factory, the `_tool_manager` wrapper), `errand/main.py` (mount and lifespan, if the app factory call moves), `errand/requirements.txt`, `errand/tests/test_mcp.py`.
- **The `421` trap re-arms.** In v1, DNS rebinding protection auto-enables when the FastMCP host defaults to localhost — errand disables it explicitly with `enable_dns_rebinding_protection=False`, and CLAUDE.md records the `421 Invalid Host header` this caused. In v2 that auto-enable **moved into `streamable_http_app()`**, which defaults to `host="127.0.0.1"`. A mounted app therefore has protection **on** unless `transport_security` is passed to the app factory. A migration that renames the import and leaves `transport_security` on the constructor either raises `TypeError` or silently restores the exact failure this repository already debugged once.
- **Dependency footprint grows.** mcp 2.x drops `httpx`/`httpx-sse` for `httpx2>=2.5.0`. errand pins `httpx==0.28.1` and imports it in at least ten modules, so the image will carry both. Not a conflict, but `address-security-review-findings` is about to rewrite `read_url`'s redirect handling on httpx — worth knowing before both land. mcp 2.x also requires `pydantic>=2.12.0`; errand's floor is `>=2.11.0`.
- **Tool errors become less informative to the caller.** v2.1.0 logs handler exceptions once server-side at ERROR with traceback and returns clients a generic `"Error executing tool <name>"`. errand's tools mostly return errors as JSON strings rather than raising, so the blast radius should be small — but the task-runner has error-driven behaviour (auto-enable-on-error tool recovery), and that path deserves checking rather than assuming.
- **Breaking**: none intended for MCP clients. The endpoint, auth, tool names and tool signatures are unchanged. If anything observable changes, the migration is wrong.
- **Not urgent**: v1.x keeps receiving security patches. This can wait for a quiet slot; it should not wait a year.
