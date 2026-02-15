## MODIFIED Requirements

### Requirement: Skill data structure
Each skill SHALL be stored as a row in the `skills` table with the following fields: `id` (UUID, auto-generated primary key), `name` (string, unique, not null, validated against Agent Skills naming rules), `description` (string, not null, max 1024 characters), `instructions` (string, not null — the SKILL.md markdown body), `created_at` (timestamp with timezone), and `updated_at` (timestamp with timezone). Skill files SHALL be stored in a `skill_files` table with fields: `id` (UUID, auto-generated primary key), `skill_id` (UUID, foreign key to skills with CASCADE delete), `path` (string, not null — relative path within the skill directory), `content` (string, not null), and `created_at` (timestamp with timezone). The combination of `skill_id` and `path` SHALL be unique.

#### Scenario: Skill structure
- **WHEN** a skill is stored in the skills table
- **THEN** it contains `id`, `name`, `description`, `instructions`, `created_at`, and `updated_at` fields

#### Scenario: Skill file structure
- **WHEN** a file is attached to a skill
- **THEN** it is stored in the skill_files table with `id`, `skill_id`, `path`, `content`, and `created_at` fields

#### Scenario: No skills exist
- **WHEN** the skills table is empty
- **THEN** the system treats the skill list as empty

### Requirement: Skills included in settings API
The `GET /api/settings` endpoint SHALL no longer return a `skills` array. Skills SHALL be managed exclusively through the dedicated skills API (`/api/skills`). The `PUT /api/settings` endpoint SHALL ignore any `skills` field in the request body.

#### Scenario: Get settings does not include skills
- **WHEN** an authenticated user calls `GET /api/settings`
- **THEN** the response does not contain a `skills` field

#### Scenario: Put settings ignores skills field
- **WHEN** an admin calls `PUT /api/settings` with a body containing a `skills` field
- **THEN** the skills field is ignored and no skills are modified

## MODIFIED Requirements

### Requirement: Skills management UI
The settings page SHALL include an always-visible "Skills" section (not collapsible) within the "Agent Configuration" group, positioned after the System Prompt section. The section SHALL display all defined skills loaded from `GET /api/skills`. The section SHALL allow the admin to add a new skill (providing name, description, and instructions), edit an existing skill, delete a skill, and manage attached files (add and remove files in `scripts/`, `references/`, and `assets/` subdirectories). Each skill in the list SHALL display its name and description. The instructions field SHALL use a multi-line textarea. The name field SHALL display validation hints indicating Agent Skills naming rules (lowercase, hyphens only, max 64 chars). The description field SHALL display a character counter (max 1024).

#### Scenario: Skills section visible on settings page
- **WHEN** an admin navigates to the settings page
- **THEN** an always-visible "Skills" section is displayed showing the count of defined skills

#### Scenario: Add a new skill
- **WHEN** the admin clicks "Add Skill" and fills in name "researcher", description "Conducts web research", and instructions "You are a research specialist..."
- **THEN** the skill is created via `POST /api/skills` and appears in the list

#### Scenario: Edit an existing skill
- **WHEN** the admin clicks edit on a skill and changes its instructions
- **THEN** the updated skill is saved via `PUT /api/skills/{id}`

#### Scenario: Delete a skill
- **WHEN** the admin clicks delete on a skill and confirms
- **THEN** the skill is removed via `DELETE /api/skills/{id}` and disappears from the list

#### Scenario: Skill name validation in UI
- **WHEN** the admin types "My Skill" in the name field
- **THEN** the UI displays a validation error indicating the name must be lowercase with hyphens only

#### Scenario: Skill name with consecutive hyphens rejected
- **WHEN** the admin types "code--review" in the name field
- **THEN** the UI displays a validation error

#### Scenario: Description character counter
- **WHEN** the admin types in the description field
- **THEN** a character counter displays the current length out of 1024

#### Scenario: Add file to skill
- **WHEN** the admin opens a skill's file manager and adds a file with path "scripts/search.py" and content
- **THEN** the file is saved via `POST /api/skills/{id}/files` and appears in the file list

#### Scenario: Delete file from skill
- **WHEN** the admin clicks delete on a file in a skill's file manager
- **THEN** the file is removed via `DELETE /api/skills/{id}/files/{file_id}`

#### Scenario: File path validation
- **WHEN** the admin tries to add a file with path "other/file.txt"
- **THEN** the UI displays a validation error indicating the path must be in scripts/, references/, or assets/
