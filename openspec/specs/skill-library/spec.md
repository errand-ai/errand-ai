## Requirements

### Requirement: Skill data structure
Each skill SHALL be a JSON object with the following fields: `id` (UUID string, auto-generated), `name` (string, unique, non-empty), `description` (string, non-empty, brief summary for discovery), and `instructions` (string, non-empty, full prompt text). Skills SHALL be stored as a JSON array under the `skills` key in the `Setting` table.

#### Scenario: Skill structure
- **WHEN** a skill is stored in settings
- **THEN** it contains `id`, `name`, `description`, and `instructions` fields

#### Scenario: Skills key not yet set
- **WHEN** no `skills` key exists in the Setting table
- **THEN** the system treats the skill list as an empty array

### Requirement: Skills included in settings API
The `GET /api/settings` endpoint SHALL return the `skills` array in its response. The `PUT /api/settings` endpoint SHALL accept a `skills` field containing the full skills array and persist it to the `Setting` table under the `skills` key. Saving skills SHALL require admin role.

#### Scenario: Get settings includes skills
- **WHEN** an authenticated user calls `GET /api/settings` and two skills are defined
- **THEN** the response includes a `skills` array with both skill objects

#### Scenario: Get settings with no skills defined
- **WHEN** an authenticated user calls `GET /api/settings` and no skills key exists
- **THEN** the response includes `skills` as an empty array

#### Scenario: Save skills via settings
- **WHEN** an admin calls `PUT /api/settings` with `{"skills": [{"id": "...", "name": "researcher", "description": "Web research skill", "instructions": "You are a research assistant..."}]}`
- **THEN** the skills array is persisted and returned in subsequent `GET /api/settings` responses

#### Scenario: Non-admin cannot save skills
- **WHEN** a non-admin user calls `PUT /api/settings` with a `skills` field
- **THEN** the request is rejected with HTTP 403

### Requirement: Skills management UI
The settings page SHALL include a collapsible "Skills" section that displays all defined skills. The section SHALL allow the admin to add a new skill (providing name, description, and instructions), edit an existing skill, and delete a skill. Each skill in the list SHALL display its name and description. The instructions field SHALL use a multi-line textarea.

#### Scenario: Skills section visible on settings page
- **WHEN** an admin navigates to the settings page
- **THEN** a "Skills" section is visible (collapsed or expanded) showing the count of defined skills

#### Scenario: Add a new skill
- **WHEN** the admin clicks "Add Skill" and fills in name "researcher", description "Conducts web research", and instructions "You are a research specialist..."
- **THEN** the skill is added to the list and saved to the backend

#### Scenario: Edit an existing skill
- **WHEN** the admin clicks edit on a skill and changes its instructions
- **THEN** the updated skill is saved to the backend

#### Scenario: Delete a skill
- **WHEN** the admin clicks delete on a skill and confirms
- **THEN** the skill is removed from the list and the change is saved to the backend

#### Scenario: Skill name uniqueness
- **WHEN** the admin tries to add a skill with a name that already exists
- **THEN** the UI shows a validation error and does not save
