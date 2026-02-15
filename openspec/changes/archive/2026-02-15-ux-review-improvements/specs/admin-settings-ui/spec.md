## MODIFIED Requirements

### Requirement: Settings page layout
The Settings page SHALL be implemented as an orchestrator component (~80 lines) that loads settings on mount and delegates rendering to child components. The page SHALL display a heading "Settings" and organise its sections into three labelled groups. The **"Agent Configuration"** group SHALL contain "System Prompt", "Skills", "Skills Repository" (if the `git-sourced-skills` change is applied), and "LLM Models" sections. The **"Task Management"** group SHALL contain a single consolidated card with "Timezone", "Task Archiving", and "Task Runner" settings separated by `divide-y divide-gray-100` dividers. The **"Integrations & Security"** group SHALL contain "MCP API Key", "Git SSH Key", and "MCP Server Configuration" sections.

Each settings section SHALL be a separate Vue component in `frontend/src/components/settings/`:
- `SystemPromptSettings.vue`
- `SkillsSettings.vue`
- `LlmModelSettings.vue`
- `TaskManagementSettings.vue` (consolidated: timezone, archiving, runner log level)
- `McpApiKeySettings.vue`
- `GitSshKeySettings.vue`
- `McpServerConfigSettings.vue`

#### Scenario: Settings page renders with child components
- **WHEN** an admin views the Settings page
- **THEN** the page loads settings once and renders each section as an independent child component

#### Scenario: Consolidated Task Management card
- **WHEN** an admin views the Task Management group
- **THEN** Timezone, Task Archiving, and Task Runner settings appear in a single white card with dividers between each section

### Requirement: Consistent explicit save pattern
All settings sections SHALL use explicit Save buttons. The three previously auto-saving controls (LLM model dropdowns, Timezone dropdown, Task Runner Log Level dropdown) SHALL no longer auto-save on change. Instead, they SHALL require the user to click a Save button. Each section SHALL track whether its current values differ from the last-saved values. When a section has unsaved changes, it SHALL display a "Unsaved changes" indicator (`text-xs text-amber-600`) near its Save button.

The Settings page SHALL register a `beforeunload` event listener when any child section has unsaved changes. The listener SHALL show the browser's native "Leave page?" confirmation when the user attempts to navigate away.

#### Scenario: LLM model requires explicit save
- **WHEN** an admin changes the task processing model dropdown
- **THEN** the change is not saved until the user clicks the Save button and an "Unsaved changes" indicator appears

#### Scenario: Timezone requires explicit save
- **WHEN** an admin changes the timezone dropdown
- **THEN** the change is not saved until the user clicks the Save button

#### Scenario: Unsaved changes indicator
- **WHEN** an admin modifies any setting without saving
- **THEN** a "Unsaved changes" label appears in amber near the Save button

#### Scenario: Beforeunload guard
- **WHEN** any settings section has unsaved changes and the user attempts to navigate away
- **THEN** the browser shows a "Leave page?" confirmation dialog

#### Scenario: No guard when all saved
- **WHEN** all settings sections have their saved values unchanged
- **THEN** navigating away does not trigger any confirmation

### Requirement: Skill deletion confirmation
The Skills section SHALL display a confirmation dialog before deleting a skill. When the user clicks the Delete button on a skill, a `<dialog>` confirmation modal SHALL appear asking "Delete this skill?" with the skill name displayed. The dialog SHALL have "Cancel" and "Delete" buttons. Only clicking "Delete" in the confirmation SHALL proceed with the deletion.

#### Scenario: Delete button shows confirmation
- **WHEN** an admin clicks Delete on a skill named "twitter-poster"
- **THEN** a confirmation dialog appears with text "Delete this skill?" and the skill name "twitter-poster"

#### Scenario: Cancel preserves skill
- **WHEN** the delete confirmation dialog is shown and the user clicks Cancel
- **THEN** the dialog closes and the skill is not deleted

#### Scenario: Confirm deletes skill
- **WHEN** the delete confirmation dialog is shown and the user clicks Delete
- **THEN** the skill is deleted and a success toast is shown

### Requirement: Settings skeleton loading state
While settings are loading, the page SHALL display skeleton placeholders that match the expected card layout using `animate-pulse` on gray rounded rectangles. The "Loading settings..." text SHALL be replaced by skeleton placeholders.

#### Scenario: Skeleton shown during settings load
- **WHEN** the Settings page is fetching settings for the first time
- **THEN** skeleton card placeholders are shown instead of "Loading settings..." text

### Requirement: Settings empty state for skills
When no skills exist, the Skills section SHALL display a centered empty state with an icon, "No skills configured" text, and guidance "Add skills to give the agent specialised capabilities." instead of showing an empty list.

#### Scenario: Skills empty state
- **WHEN** the Skills section loads with zero skills configured
- **THEN** it displays a centered empty state with icon and guidance text
