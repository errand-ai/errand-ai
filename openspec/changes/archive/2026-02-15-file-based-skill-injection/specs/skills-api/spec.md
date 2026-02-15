## ADDED Requirements

### Requirement: Skill data model
The system SHALL store skills in a `skills` table with the following columns: `id` (UUID, primary key, auto-generated), `name` (text, unique, not null), `description` (text, not null), `instructions` (text, not null — the SKILL.md markdown body), `created_at` (timestamp with timezone), `updated_at` (timestamp with timezone). The `name` field SHALL be validated against Agent Skills naming rules: lowercase alphanumeric characters and hyphens only, max 64 characters, must not start or end with a hyphen, must not contain consecutive hyphens.

#### Scenario: Skill stored with valid name
- **WHEN** a skill is created with name "code-review", description "Reviews code for quality", and instructions "## Steps\n1. Read the diff..."
- **THEN** the skill is persisted with an auto-generated UUID, the provided fields, and timestamps

#### Scenario: Skill name uniqueness enforced
- **WHEN** a skill with name "research" already exists and a new skill with name "research" is created
- **THEN** the creation fails with a conflict error

### Requirement: Skill file data model
The system SHALL store skill files in a `skill_files` table with the following columns: `id` (UUID, primary key, auto-generated), `skill_id` (UUID, foreign key to skills.id with CASCADE delete), `path` (text, not null — relative path within the skill directory), `content` (text, not null — file content), `created_at` (timestamp with timezone). The `path` field SHALL be validated to ensure it is within one of the allowed subdirectories: `scripts/`, `references/`, or `assets/`. Paths SHALL be exactly one level deep (e.g. `scripts/extract.py` is valid, `scripts/lib/utils.py` is not). The combination of `skill_id` and `path` SHALL be unique.

#### Scenario: Skill file stored with valid path
- **WHEN** a file is added to skill "research" with path "scripts/search.py" and content "import requests\n..."
- **THEN** the file is persisted with an auto-generated UUID linked to the skill

#### Scenario: Invalid path rejected — wrong subdirectory
- **WHEN** a file is added with path "other/file.txt"
- **THEN** the creation fails with a validation error indicating the path must be in scripts/, references/, or assets/

#### Scenario: Invalid path rejected — nested too deep
- **WHEN** a file is added with path "scripts/lib/utils.py"
- **THEN** the creation fails with a validation error indicating paths must be one level deep

#### Scenario: Duplicate path rejected
- **WHEN** a file with path "scripts/search.py" already exists for skill "research" and another file with the same path is added
- **THEN** the creation fails with a conflict error

#### Scenario: Files deleted when skill deleted
- **WHEN** a skill with 3 attached files is deleted
- **THEN** all 3 files are also deleted (cascade)

### Requirement: Skill name validation rules
The skills API SHALL validate skill names against the Agent Skills standard rules. The name SHALL contain only lowercase letters (a-z), digits (0-9), and hyphens (-). The name SHALL NOT start or end with a hyphen. The name SHALL NOT contain consecutive hyphens (--). The name SHALL be between 1 and 64 characters. The description SHALL be between 1 and 1024 characters.

#### Scenario: Valid skill name accepted
- **WHEN** a skill is created with name "pdf-processing"
- **THEN** the skill is created successfully

#### Scenario: Uppercase rejected
- **WHEN** a skill is created with name "PDF-Processing"
- **THEN** the creation fails with a validation error: name must be lowercase

#### Scenario: Leading hyphen rejected
- **WHEN** a skill is created with name "-research"
- **THEN** the creation fails with a validation error

#### Scenario: Consecutive hyphens rejected
- **WHEN** a skill is created with name "code--review"
- **THEN** the creation fails with a validation error

#### Scenario: Name too long rejected
- **WHEN** a skill is created with a name that is 65 characters long
- **THEN** the creation fails with a validation error

#### Scenario: Description too long rejected
- **WHEN** a skill is created with a description that is 1025 characters long
- **THEN** the creation fails with a validation error

#### Scenario: Empty name rejected
- **WHEN** a skill is created with an empty name
- **THEN** the creation fails with a validation error

### Requirement: List skills endpoint
The API SHALL expose `GET /api/skills` which returns a JSON array of all skills. Each skill object SHALL include `id`, `name`, `description`, `instructions`, `created_at`, `updated_at`, and a `files` array containing each file's `id`, `path`, and `created_at` (not the file content). The endpoint SHALL require authentication. The list SHALL be ordered by name ascending.

#### Scenario: List skills with files
- **WHEN** an authenticated user calls `GET /api/skills` and two skills exist, one with 2 files
- **THEN** the response is a JSON array with both skills, each including their files array (without content)

#### Scenario: List skills empty
- **WHEN** an authenticated user calls `GET /api/skills` and no skills exist
- **THEN** the response is an empty JSON array

### Requirement: Create skill endpoint
The API SHALL expose `POST /api/skills` which creates a new skill. The request body SHALL contain `name`, `description`, and `instructions` fields. The endpoint SHALL validate the name and description against Agent Skills rules. The endpoint SHALL require admin role. On success, it SHALL return the created skill with HTTP 201.

#### Scenario: Create skill successfully
- **WHEN** an admin calls `POST /api/skills` with `{"name": "research", "description": "Conducts web research", "instructions": "## Steps\n1. Search..."}`
- **THEN** the skill is created and returned with HTTP 201 including auto-generated id and timestamps

#### Scenario: Create skill with invalid name
- **WHEN** an admin calls `POST /api/skills` with `{"name": "My Skill", ...}`
- **THEN** the request is rejected with HTTP 422 and a validation error

#### Scenario: Non-admin cannot create skill
- **WHEN** a non-admin user calls `POST /api/skills`
- **THEN** the request is rejected with HTTP 403

### Requirement: Get single skill endpoint
The API SHALL expose `GET /api/skills/{id}` which returns a single skill by UUID. The response SHALL include the skill fields and its files array (with content included for each file). The endpoint SHALL require authentication. If the skill does not exist, it SHALL return HTTP 404.

#### Scenario: Get skill with files including content
- **WHEN** an authenticated user calls `GET /api/skills/{id}` for a skill with 2 attached files
- **THEN** the response includes the skill fields and a files array with id, path, content, and created_at for each file

#### Scenario: Get non-existent skill
- **WHEN** an authenticated user calls `GET /api/skills/{id}` with a UUID that does not exist
- **THEN** the response is HTTP 404

### Requirement: Update skill endpoint
The API SHALL expose `PUT /api/skills/{id}` which updates a skill's name, description, and/or instructions. The request body MAY contain any subset of these fields. The endpoint SHALL validate any provided name and description against Agent Skills rules. The endpoint SHALL require admin role. On success, it SHALL return the updated skill.

#### Scenario: Update skill instructions
- **WHEN** an admin calls `PUT /api/skills/{id}` with `{"instructions": "## Updated\n..."}`
- **THEN** the skill's instructions are updated and the updated skill is returned

#### Scenario: Rename skill with valid name
- **WHEN** an admin calls `PUT /api/skills/{id}` with `{"name": "web-research"}`
- **THEN** the skill's name is updated

#### Scenario: Rename to duplicate name rejected
- **WHEN** an admin calls `PUT /api/skills/{id}` with a name that already belongs to another skill
- **THEN** the request is rejected with HTTP 409

### Requirement: Delete skill endpoint
The API SHALL expose `DELETE /api/skills/{id}` which deletes a skill and all its attached files (cascade). The endpoint SHALL require admin role. On success, it SHALL return HTTP 204. If the skill does not exist, it SHALL return HTTP 404.

#### Scenario: Delete skill with files
- **WHEN** an admin calls `DELETE /api/skills/{id}` for a skill with 3 attached files
- **THEN** the skill and all 3 files are deleted and HTTP 204 is returned

#### Scenario: Delete non-existent skill
- **WHEN** an admin calls `DELETE /api/skills/{id}` with a UUID that does not exist
- **THEN** the response is HTTP 404

### Requirement: Add file to skill endpoint
The API SHALL expose `POST /api/skills/{id}/files` which adds a file to a skill. The request body SHALL contain `path` (string) and `content` (string). The endpoint SHALL validate the path is within `scripts/`, `references/`, or `assets/` and is one level deep. The endpoint SHALL require admin role. On success, it SHALL return the created file with HTTP 201.

#### Scenario: Add script file
- **WHEN** an admin calls `POST /api/skills/{id}/files` with `{"path": "scripts/extract.py", "content": "#!/usr/bin/env python3\n..."}`
- **THEN** the file is created and returned with HTTP 201

#### Scenario: Add file with invalid path
- **WHEN** an admin calls `POST /api/skills/{id}/files` with `{"path": "invalid/file.txt", ...}`
- **THEN** the request is rejected with HTTP 422

#### Scenario: Add duplicate path rejected
- **WHEN** a file with path "scripts/extract.py" already exists and another file with the same path is added
- **THEN** the request is rejected with HTTP 409

### Requirement: Delete file from skill endpoint
The API SHALL expose `DELETE /api/skills/{id}/files/{file_id}` which removes a file from a skill. The endpoint SHALL require admin role. On success, it SHALL return HTTP 204.

#### Scenario: Delete file successfully
- **WHEN** an admin calls `DELETE /api/skills/{id}/files/{file_id}` for an existing file
- **THEN** the file is deleted and HTTP 204 is returned

#### Scenario: Delete file from wrong skill
- **WHEN** an admin calls `DELETE /api/skills/{id}/files/{file_id}` where the file belongs to a different skill
- **THEN** the response is HTTP 404

### Requirement: Alembic migration for skills tables
The system SHALL include an Alembic migration that creates the `skills` and `skill_files` tables. The migration SHALL also move any existing skills from `Setting(key="skills")` to the new `skills` table, auto-slugifying non-compliant names (e.g. "My Skill" → "my-skill"). If two skills slugify to the same name, a numeric suffix SHALL be appended (e.g. "my-skill-2"). After migration, the `skills` key SHALL be removed from the settings table.

#### Scenario: Migration creates tables
- **WHEN** the migration runs on a database with no skills or skill_files tables
- **THEN** both tables are created with the correct schema

#### Scenario: Migration moves existing skills
- **WHEN** the migration runs and `Setting(key="skills")` contains `[{"id": "abc", "name": "Research Helper", "description": "Helps research", "instructions": "..."}]`
- **THEN** a skill is created with name "research-helper", the original description and instructions, and the settings key is removed

#### Scenario: Migration handles name conflicts
- **WHEN** the migration runs and two existing skills slugify to the same name "my-skill"
- **THEN** the first becomes "my-skill" and the second becomes "my-skill-2"

#### Scenario: Migration on empty database
- **WHEN** the migration runs and no `skills` key exists in settings
- **THEN** the tables are created empty and no data migration occurs
