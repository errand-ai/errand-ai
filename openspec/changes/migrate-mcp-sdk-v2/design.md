## Context

errand's MCP server is pinned to mcp v1 by an upper bound added in an emergency on 2026-07-28. The bound is right and upstream recommends it. This change removes the reason for it.

The shape of the work is unusual in a helpful way: the SDK's breaking change is almost entirely a rename, and errand's usage sits almost entirely in the part that did not break. Four imports, one constructor, one app factory, one private-API monkeypatch. Thirty-five tool handlers that do not change at all.

What makes it worth designing rather than just doing is that two of the moving pieces are exactly the pieces that have bitten this repository before — the DNS-rebinding `421`, and an mcp version bump landing without anyone noticing what it touched.

## Goals / Non-Goals

**Goals:**

- `errand/mcp_server.py` runs on mcp 2.x, and the `<2` bound is removed because it is no longer needed rather than because someone found it inconvenient.
- No observable change for MCP clients: same endpoint, same auth, same 35 tools with the same names and signatures.
- The `mcp-server-endpoint` spec describes the code, for the first time since 2026-02-13.
- The reason the old bound existed is preserved in the history, not deleted with the line.

**Non-Goals:**

- Migrating `task-runner` or `evals` to mcp v2. Both are clients, both are constrained elsewhere, and MCP is a wire protocol.
- Adopting anything v2 newly offers — `Client`, middleware, extensions, resource security, the 2026-07-28 stateless protocol. This change swaps the SDK and stops.
- Fixing the unbounded `mcp>=1.0.0` in `task-runner/requirements.txt`. Adjacent, real, and smaller than this; it should land on its own.
- Restructuring the tool surface while it happens to be open.

## Decisions

**Migrate the server only, and leave both clients on v1.** MCP is a wire protocol; a v1 client talking to a v2 server is the arrangement the spec exists to make possible. The task-runner cannot easily move anyway — it reaches the SDK through `agents.mcp.MCPServerStreamableHttp`, and `openai-agents` declares `mcp<2,>=1.19.0`, so its version is not errand's to choose. Migrating all three together would triple the change for no benefit and would block on an upstream constraint. The cost is that cross-version compatibility becomes an assumption, which is why it is a verification task and not a footnote.

**Pass `transport_security` to `streamable_http_app()` explicitly, and treat that as the centre of the change rather than a detail.** In v1 the DNS-rebinding auto-enable lives on the constructor, where errand disables it. In v2 it lives in `streamable_http_app()`, which defaults to `host="127.0.0.1"`, so a mounted app gets protection switched **on** by default. The guide is direct about the consequence: the auto-allowlist entries are `host:port` patterns, so a request whose `Host` header carries no port is rejected with `421 Invalid Host header`. CLAUDE.md already documents that 421 as something this repository debugged. The failure mode of getting this wrong is not a crash at deploy — it is every MCP request failing after the app comes up healthy, which is the worst shape a regression can have.

**Write the test for the 421 before the migration, not after.** A test that asserts a real `Host` header is accepted at `/mcp` will pass on v1, fail the moment the constructor keyword is dropped, and pass again when it is moved to the app factory. That sequence is the only thing that proves the parameter actually landed somewhere effective. Asserting it after the fact proves only that the current arrangement works, which is what a green suite would say either way.

**Decide the `_tool_manager` wrapper deliberately rather than discovering it.** `errand/mcp_server.py:70` wraps `mcp._tool_manager.call_tool` to log which tool is being invoked. That is private API, and the migration guide — which is otherwise thorough about private moves, naming `_mcp_server` → `_lowlevel_server` — says nothing about `_tool_manager`. Silence is not a guarantee. Two options: keep the wrapper if the attribute survives, or replace the logging with v2's `middleware` constructor parameter, which is the supported way to do this and did not exist in v1. Preference is the middleware, because a private-attribute wrapper is how this breaks again on 3.0. But that is a bigger diff than a rename, so it is a decision to take on evidence once the attribute's fate is known, not in advance.

**Take `mcp>=2.1.1,<3`, not an exact pin and not an open upper bound.** `>=2.1.1` because 2.1.1 and 2.0.1 carry the improved `ModuleNotFoundError` and 2.1.0 carries the server-side exception logging — there is no reason to start below them. `<3` because the whole point of this change is that an unbounded major is how errand lost a day. The bound is the lesson, not the version.

**Do not migrate to capture a security fix, because there isn't one.** v1.x remains a maintenance line receiving critical bug fixes and security patches; 1.29.1 shipped 2026-08-24. Anyone justifying this work on security grounds is reaching. The justification is that the surface is small now and grows monotonically.

## Risks / Trade-offs

**DNS rebinding protection silently re-enables and every MCP request returns 421** → The highest-severity risk and the most likely to reach production, because the app starts healthy and the failure is per-request. Mitigated by writing the `Host`-header test first (see Decisions) and by an explicit post-deploy check against the real hostname, not a localhost smoke test.

**`mcp._tool_manager` does not survive and the failure is a startup `AttributeError`** → Loud and immediate, so low severity despite being the most likely thing to break. It is called out here only so the fix is a decision already taken rather than an improvisation at the point of failure.

**A v1 client cannot talk to the v2 server** → Would break the task-runner completely, i.e. every task. Considered unlikely — this is the compatibility MCP's versioning exists to provide, and v2 adds protocol support rather than dropping it — but "unlikely and total" is exactly the combination that justifies an explicit end-to-end task run before merge rather than a unit test.

**`httpx` and `httpx2` both in the image** → Larger image, two HTTP stacks, and a future reader unsure which one a given module uses. Accepted: `httpx2` arrives as an mcp dependency, not a choice, and errand's own code keeps using `httpx`. Worth revisiting only if errand ever wants to consolidate.

**Colliding with `address-security-review-findings`** → That change rewrites `read_url`'s redirect handling on `httpx` and touches `mcp_server.py`, which this change also touches. Sequential development is the house rule, so the conflict is procedural rather than technical — but whichever lands second rebases onto a changed `mcp_server.py`, and the SSRF work is the more delicate of the two. This should go second.

**Tool error messages become generic and something downstream was parsing them** → v2.1.0 returns clients `"Error executing tool <name>"` and keeps the traceback server-side. errand's tools mostly return errors as JSON strings rather than raising, so most paths are unaffected, but the task-runner's auto-enable-on-error recovery reacts to tool failures and has not been checked against this.

## Migration Plan

No schema change, no configuration change, no data migration. One version bump, one deploy.

Order within the change: the `Host`-header test first, then imports, then the constructor-to-app-factory move, then the `_tool_manager` decision, then the requirement, then the spec.

Order relative to other work: after `update-vulnerable-dependencies` (which must not be complicated by an SDK major) and after `address-security-review-findings` (which touches the same file and is the more delicate change).

Rollback is a version revert. The old `mcp[http]>=1.23.2,<2` line must come back exactly, `[http]` extra included — reverting to `mcp>=1.23.2,<2` without the extra would leave v1 without its HTTP dependencies.

## Open Questions

- **Does `mcp._tool_manager` survive in v2?** Determines whether the call logging stays a wrapper or becomes `middleware`. Answerable in minutes against an installed 2.1.1; deliberately not answered here so the answer comes from the SDK rather than from inference.
- **Should the call logging move to `middleware` regardless?** Even if the private attribute survives, `middleware` is the supported seam and did not exist when this wrapper was written. The wrapper is a known future breakage.
- **Does the task-runner's error recovery depend on tool error text?** If it matches on message content, v2.1.0's generic `"Error executing tool <name>"` changes what it sees. Cheap to check, easy to miss.
- **Should `errand/requirements.txt` raise its `pydantic>=2.11.0` floor to the `>=2.12.0` mcp 2.x requires?** pip will resolve it upward regardless, so this is about whether the file states its real minimum or leaves it implied.
