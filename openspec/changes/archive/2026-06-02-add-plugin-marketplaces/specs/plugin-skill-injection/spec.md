## ADDED Requirements

### Requirement: Worker discovers plugin-sourced skills from cache
For each plugin row with `enabled=true` (filtered further by per-profile `enabled_plugins`), the worker SHALL walk the plugin's cache directory and discover skills under `skills/<name>/SKILL.md`. Each discovered skill SHALL be represented as a structure with `name`, `description` (parsed from SKILL.md frontmatter), `instructions` (the SKILL.md body), and `files` (any sibling files under the skill directory).

#### Scenario: Plugin contributes skills
- **WHEN** a plugin's cache directory contains `skills/post-message/SKILL.md` and `skills/react-to-thread/SKILL.md`
- **THEN** the worker discovers two skills named `post-message` and `react-to-thread`

#### Scenario: Plugin contains no skills directory
- **WHEN** a plugin's cache directory has no `skills/` subdirectory
- **THEN** the worker contributes zero plugin skills for that plugin

#### Scenario: Skill subdirectory missing SKILL.md
- **WHEN** a plugin contains `skills/foo/` without a `SKILL.md` file
- **THEN** the worker skips that directory and logs at warning level

### Requirement: Plugin skills merged into skill tarball with precedence
The worker SHALL merge skills in the following precedence order, where higher-precedence sources win when names collide: DB skills > plugin skills > git-sourced skills > system skills. The merged set SHALL be written into the per-task workspace tarball at `/workspace/skills/`.

#### Scenario: DB skill wins over plugin skill
- **WHEN** a DB skill `slack` exists and a plugin also contributes `slack`
- **THEN** the DB version is included and a warning is logged

#### Scenario: Plugin skill wins over git skill
- **WHEN** a plugin contributes `notify` and the git skills repo also defines `notify`
- **THEN** the plugin version is included and a warning is logged

#### Scenario: Plugin skill wins over system skill
- **WHEN** a plugin contributes `repo-context` and a system skill of the same name exists
- **THEN** the plugin version is included and a warning is logged

#### Scenario: No collisions
- **WHEN** all skill names across sources are unique
- **THEN** every skill is included with no warnings

### Requirement: Plugin-vs-plugin collision resolved by alphabetical plugin name
When two enabled plugins contribute skills with the same name, the worker SHALL select the skill from the plugin whose `plugin_name` sorts earliest alphabetically (using standard Unicode code-point ordering). A warning SHALL be logged naming both plugins and the chosen winner.

#### Scenario: Alphabetical tiebreak
- **WHEN** plugins `slack-toolkit` and `team-chat` both define `post-message`
- **THEN** `slack-toolkit`'s version is included and a warning is logged

#### Scenario: Three-way collision
- **WHEN** plugins `acme`, `bravo`, and `charlie` all define `notify`
- **THEN** `acme`'s version is included and warnings are logged for the other two

### Requirement: Plugin skills appear in system prompt manifest
Plugin-sourced skills SHALL appear in the skill discovery manifest in the system prompt with the same shape as DB, git, and system skills (name and description). The manifest SHALL annotate each plugin-sourced entry with its source plugin name.

#### Scenario: Manifest lists plugin skills
- **WHEN** the worker prepares the system prompt and a plugin `slack-toolkit` contributes a `post-message` skill
- **THEN** the manifest includes an entry for `post-message` annotated as sourced from `slack-toolkit`

### Requirement: Plugin skills disabled when plugin disabled
When a plugin row has `enabled=false`, none of its skills SHALL be discovered for any task.

#### Scenario: Disabled plugin contributes nothing
- **WHEN** a plugin row has `enabled=false`
- **THEN** the worker does not walk that plugin's cache directory and contributes zero skills for it
