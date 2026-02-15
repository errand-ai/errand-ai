## Context

The content-manager's task runner agent currently discovers and loads skills via MCP tool calls (`list_skills`, `get_skill`) to the backend. This requires the container to have network access back to the backend, an MCP API key, and relies on the agent obeying a system prompt directive to call the tools. Skills are stored as a JSON array in the settings table (`Setting(key="skills")`), with each skill being `{id, name, description, instructions}`.

We are adopting the [Agent Skills standard](https://agentskills.io/specification) to structure skills as directories with a `SKILL.md` manifest and optional `scripts/`, `references/`, `assets/` subdirectories. The worker will write these directories into the container filesystem, eliminating the MCP-based skill delivery entirely.

## Goals / Non-Goals

**Goals:**
- Full compliance with the Agent Skills directory format specification
- Support `scripts/`, `references/`, and `assets/` subdirectories from day one
- Dedicated data model and API for skills (not crammed into settings JSONB)
- File management UI for uploading and organising skill files
- Progressive disclosure in the container: metadata in system prompt, full SKILL.md on demand, resources on demand
- Eliminate MCP round-trips and network dependency for skill delivery
- Settings page reorganisation into logical groups

**Non-Goals:**
- Uploading skills to OpenAI's hosted skills API (their native skills feature requires the ShellTool/Responses API and would create provider lock-in)
- Binary file support in skill files (text files only — scripts, markdown, config)
- Skill versioning (the Agent Skills spec supports it but we don't need it yet)
- Import/export of skill zip bundles (future iteration)
- Skill marketplace or sharing between instances

## Decisions

### D1: Dedicated tables vs settings JSONB for skill storage

**Decision**: New `skills` and `skill_files` tables with a proper relational model.

**Alternatives considered**:
- Keep in settings JSONB with files as base64 — poor query performance, JSONB bloat, no referential integrity
- Single table with file content in a JSONB column — awkward to query individual files, size limits

**Rationale**: Skills with attached files are a first-class entity, not a configuration value. Separate tables give us FK constraints, individual file CRUD, and clean queries from the worker. The `skill_files` table stores text content directly (no binary/blob), keeping it simple.

### D2: File storage approach — database text vs object storage

**Decision**: Store file content as text in the `skill_files` table (TEXT column).

**Alternatives considered**:
- Object storage (S3/MinIO) — adds infrastructure dependency, overkill for text files
- Filesystem storage on a PV — state management complexity, backup concerns
- Git repository — interesting but adds git dependency to the backend

**Rationale**: Skill files are text (scripts, markdown, config). They're small (the spec recommends SKILL.md under 500 lines, ~5000 tokens). Storing in PostgreSQL keeps the architecture simple with no new infrastructure. If binary assets become needed later, we can add object storage.

### D3: File path validation — allowed subdirectories

**Decision**: File paths must be in one of three subdirectories: `scripts/`, `references/`, `assets/`. Paths are validated to prevent directory traversal. Files are one level deep (e.g. `scripts/extract.py`, not `scripts/lib/utils.py`).

**Rationale**: Matches the Agent Skills spec exactly. One-level depth keeps things simple and avoids complex tree management in the UI. The spec says "keep file references one level deep from SKILL.md."

### D4: Skills API authentication — same as settings

**Decision**: Skills API endpoints require admin role (same as settings). Use the existing `require_admin` dependency.

**Rationale**: Skills define agent behaviour — same sensitivity level as the system prompt. No reason to use different auth.

### D5: Worker skill assembly — tar archive approach

**Decision**: The worker builds a tar archive containing the full `/workspace/skills/` directory tree and writes it to the container via `put_archive()` (same pattern used for prompt files and SSH keys today).

The directory structure in the container:
```
/workspace/skills/
  <name>/
    SKILL.md          # Generated from DB: frontmatter (name, description) + body (instructions)
    scripts/          # Files from skill_files where path starts with scripts/
      extract.py
    references/       # Files from skill_files where path starts with references/
      REFERENCE.md
    assets/           # Files from skill_files where path starts with assets/
      template.json
```

**Rationale**: Reuses the existing `put_archive()` pattern. The worker already builds tar archives for prompt files — extending this to include skill directories is minimal code change.

### D6: System prompt skill manifest format

**Decision**: When skills exist, append a `## Skills` section to the system prompt containing a compact manifest and a directive:

```
## Skills

Available skills are installed at /workspace/skills/. Each skill directory contains a SKILL.md file with full instructions, and may include scripts/, references/, and assets/ subdirectories.

| Skill | Description |
|-------|-------------|
| research | Conducts web research on a topic |
| code-review | Reviews code for quality and best practices |

If a skill is relevant to your task, read its SKILL.md file to load the full instructions before proceeding.
```

**Rationale**: The manifest uses ~100 tokens (matching the spec's progressive disclosure guidance). The table format is compact and scannable. The agent uses `execute_command` to `cat /workspace/skills/<name>/SKILL.md` when it decides a skill is relevant — no new tools needed.

### D7: Data migration from settings to skills tables

**Decision**: An Alembic migration creates the new tables and moves existing skills from `Setting(key="skills")` to the `skills` table. Non-compliant names (uppercase, spaces) are auto-slugified during migration (e.g. "My Skill" → "my-skill"). The old `skills` key is removed from the settings table after migration.

**Rationale**: Clean break — no dual-path code needed. Existing skills are preserved. Auto-slugification is safer than requiring manual rename.

### D8: Settings page reorganisation

**Decision**: Group settings into three sections with header labels:
1. **Agent Configuration**: System Prompt, Skills, LLM Models
2. **Task Management**: Task Archiving, Task Runner (log level), Timezone
3. **Integrations & Security**: MCP API Key, Git SSH Key, MCP Server Configuration

Skills section is always expanded (not collapsible), positioned directly after System Prompt.

**Rationale**: Groups related settings logically. Skills are core agent behaviour — they belong next to the system prompt, not buried in a collapsible section.

## Risks / Trade-offs

- **[Migration risk] Existing skills may have non-compliant names** → Auto-slugify during migration. Log warnings for any name conflicts after slugification. If two skills slugify to the same name, append a numeric suffix.
- **[Scale risk] Many large skill files in DB could slow worker queries** → Acceptable for now (expect <20 skills with <10 files each). Add pagination/lazy loading if this becomes an issue.
- **[Text-only files] Cannot store binary assets (images, compiled scripts)** → Intentional limitation. The Agent Skills spec lists images as a valid asset type, but our use case is text-centric. Can add binary support later if needed.
- **[No rollback for MCP removal] Removing list_skills/get_skill breaks any external MCP clients using them** → Low risk — these tools were only used by our own task runner, not external consumers. The MCP server retains its other tools.
- **[UI complexity] File management adds significant UI surface area** → Keep it simple: flat file list per skill, upload button, delete button. No inline editing of uploaded files (edit SKILL.md body only). Files are uploaded as text and displayed as read-only.

## Migration Plan

1. **Alembic migration**: Create `skills` and `skill_files` tables. Migrate data from `Setting(key="skills")`. Drop the settings key.
2. **Deploy backend**: New skills API endpoints available. Worker uses new skill assembly path. MCP tools removed.
3. **Deploy frontend**: Settings page reorganised. Skills UI uses new API with file management.
4. **Verify**: Confirm existing skills are intact in new tables. Test skill injection into container. Test file upload/download.

Rollback: Revert Alembic migration (down migration recreates settings key from skills table data).
