## Context

The task-runner's `discover_tools` native tool was introduced as part of the lazy MCP tool loading optimisation: instead of loading all MCP tool schemas into every turn's context, a compact `<available_mcp_tools>` catalog is injected into the system prompt and the agent enables individual tools on demand by calling `discover_tools(["<name>"])`.

In parallel, the worker writes Agent Skills into the container at `/workspace/skills/<name>/SKILL.md` and surfaces them via a separate Markdown "## Skills" table in the system prompt. Skill activation is just "read the SKILL.md file" — there is no discovery verb.

The two surfaces look almost identical to a model:

```
## Skills                       ← read the file
| tweet-publisher | … |
| gws-drive       | … |

<available_mcp_tools>           ← call discover_tools FIRST
- post_tweet: …
</available_mcp_tools>
```

Less-capable models collapse both into one "named capability" concept and reach for the loudest activation verb — `discover_tools` — for both. The current response (`"Not found: <name>"`) reads as terminal, and the model abandons the task. Production logs (Loki, last 7 days) show this on multiple Twitter/Drive-related profiles.

PR #178 fixed a similar failure for native tools that did not appear in `all_known_tools` by adding an `always_on_tools` set; this change extends the same defensive-recovery pattern to skills.

## Goals / Non-Goals

**Goals:**
- Skill-name probes through `discover_tools` recover in-band: the tool result contains the matched `SKILL.md` content so the model can act on it the same turn.
- Strong models are unaffected: they continue to use `read_file` on the SKILL.md path and never trigger the new code path.
- No model classification, tiering, or per-profile setting required.
- The change is observable: skill matches are surfaced in the tool result with a distinct `Loaded skill:` clause so it shows up cleanly in tool-call logs.

**Non-Goals:**
- Reworking the skill manifest in the system prompt (no prompt changes in this change).
- Adding a new native tool such as `load_skill` — the recovery happens inside the existing `discover_tools`.
- Changing how skills get into `/workspace/skills/` (the agent-skill-loading capability is untouched).
- Per-model "verbose vs concise" prompt tiering — out of scope; revisit only if recovery telemetry says A1/A2 isn't enough.
- Sending the SKILL.md content through any other transformation (truncation, summarisation) before returning it.

## Decisions

### Decision 1: Inline `SKILL.md` content in the tool result rather than return a hint

**Choice (A2):** When `discover_tools(["tweet-publisher"])` matches a skill, the response includes the literal contents of `/workspace/skills/tweet-publisher/SKILL.md` so the model can use the instructions immediately.

**Alternative considered (A1):** Return a hint such as *"tweet-publisher is a skill; read /workspace/skills/tweet-publisher/SKILL.md to load it."*

**Rationale:** The model is, by definition, already in a confused state when it hit this path. A model that conflated skill and tool names probably will not reliably chain a `read_file` call next — it might re-probe `discover_tools` instead. Inlining the SKILL.md ends the failure on the current turn. The extra tokens are bounded (SKILL.md files are typically under 4 KB) and only paid on the recovery path.

### Decision 2: Populate `installed_skills` at agent construction, not inside `discover_tools`

**Choice:** Scan `/workspace/skills/*/SKILL.md` once at task-runner startup (in `main.py`) and pass the resulting `dict[str, str]` (name → absolute path) into `ToolVisibilityContext`. `discover_tools` performs only a dict lookup and a synchronous file read on a positive match.

**Alternative considered:** Have `discover_tools` walk `/workspace/skills/` on every call.

**Rationale:** Avoid per-call directory scanning. The skill set is fixed for the lifetime of the task. Matching the existing pattern (`all_known_tools` is also populated at startup) keeps `discover_tools` a pure function over its context.

### Decision 3: Read `SKILL.md` synchronously inside `discover_tools`

**Choice:** Use a blocking read. `discover_tools` is already a sync `@function_tool` (returns `str`, not `Coroutine[..., str]`).

**Alternative considered:** Pre-load all SKILL.md contents into memory at startup and store them in `installed_skills` as `dict[str, str]` (name → content).

**Rationale:** Lazy file reads avoid loading SKILL.md for skills the agent never probes. The agent only triggers the recovery path on a name collision, which is rare on strong models. SKILL.md files are small (typically <4 KB) — a single sync read on the recovery path is acceptable. If the file disappears between startup and the call, the tool returns `Not found:` for that name (same as today) and continues.

### Decision 4: New `Loaded skill:` response clause; preserve `Not found:` wording

**Choice:** The response gains a fourth clause, in the order `Enabled` → `Already enabled (always-on)` → `Loaded skill` → `Not found`. Each clause is omitted when its bucket is empty.

`Not found:` keeps its exact existing wording so existing log filters, alerts, and recovery code (e.g. PR #178's `ModelBehaviorError` handler) continue to fire on truly-unknown names.

For a `Loaded skill:` entry, the clause is followed by the file's contents inside a fenced delimiter so the model can parse where the SKILL.md ends:

```
Loaded skill: tweet-publisher

--- /workspace/skills/tweet-publisher/SKILL.md ---
<contents>
--- end skill ---
```

Multiple skill matches in the same call concatenate their delimited blocks.

**Alternative considered:** Repurpose `Not found:` to carry the SKILL.md content (overloading semantics).

**Rationale:** A distinct clause keeps tool-result parsers and downstream logging unambiguous; matches the existing additive-clause pattern from PR #178.

### Decision 5: Skill names take precedence over `Not found`; no precedence vs catalog/always-on

**Choice:** Outcome priority becomes: `always_on_tools` > `all_known_tools` > `installed_skills` > `Not found`. A name that is both a real tool and a skill (extremely unlikely, but possible) is classified as the tool. The `Loaded skill:` clause only fires for names that would otherwise be `Not found`.

**Rationale:** Preserves today's behaviour for any real tool, and avoids paying SKILL.md read cost on every successful tool discovery.

## Risks / Trade-offs

- **[Risk] Strong models that previously got `Not found` for a typo now get a skill loaded instead.** → Mitigation: real skills the agent didn't intend to use are harmless — at worst the model has slightly more context. Not a behaviour regression.

- **[Risk] Path traversal via skill name lookup.** → Mitigation: `installed_skills` is a closed dict populated at startup from a fixed directory scan. The tool never concatenates user input into a path; it only looks up an exact-string key in the dict.

- **[Risk] Large `SKILL.md` files (e.g. > 50 KB) bloat tool results.** → Mitigation: SKILL.md content is authored by the operator and is already injected into other contexts in larger forms elsewhere. If oversize files become a problem, add a soft cap in a follow-up; not in this change.

- **[Trade-off] Recovery path masks a real bug if the operator names a real MCP tool with the same string as a skill.** → Mitigation: tool-name precedence (Decision 5) ensures real tools always win. The clash would only manifest if the tool exists and the model still gets `Not found` — which cannot happen because we resolve catalog membership first.

- **[Risk] `installed_skills` drifts from `/workspace/skills/` if files are added at runtime.** → Mitigation: by design, skills are immutable for the lifetime of a task. Out of scope.

## Migration Plan

No data, schema, or API migration. Ship as a single PR:

1. Add `installed_skills: dict[str, str]` field to `ToolVisibilityContext` (default empty dict).
2. Extend `discover_tools` with the skill-match recovery path.
3. Populate `installed_skills` in `task-runner/main.py` from `/workspace/skills/*/SKILL.md` at agent construction.
4. Add unit tests covering: pure skill match, mixed enable+skill+not-found, skill-name collision with tool name (tool wins), missing SKILL.md at probe time, and idempotent multi-name probe.

Rollback: revert the PR; no data side-effects.

## Open Questions

- None blocking. Soft caps on SKILL.md size or telemetry on recovery hits are deferred to a follow-up once we see the impact in production logs.
