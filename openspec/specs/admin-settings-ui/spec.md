## Purpose

Admin settings page navigation layout and sub-page structure.
## Requirements
### Requirement: Settings page layout

The Settings page SHALL use a responsive navigation layout that switches between sidebar and dropdown modes based on viewport width. At viewport widths ≥ 640px (Tailwind `sm` breakpoint) the page SHALL render the existing sidebar layout to the left of content. At viewport widths < 640px the page SHALL render a section picker dropdown above the content area, with the sidebar hidden.

The eight settings sub-pages and their section composition SHALL be unchanged: "Agent Configuration" (`/settings/agent`), "Task Management" (`/settings/tasks`), "Security" (`/settings/security`), "Task Profiles" (`/settings/profiles`), "Integrations" (`/settings/integrations`), "Task Generators" (`/settings/task-generators`), "Cloud Service" (`/settings/cloud`), and "User Management" (`/settings/users`).

#### Scenario: Sidebar visible on tablet/desktop
- **WHEN** an admin navigates to `/settings/*` on a viewport with `min-width: 640px`
- **THEN** the page SHALL render a left-hand sidebar listing all settings sections
- **AND** the section picker dropdown SHALL be hidden

#### Scenario: Dropdown visible on mobile
- **WHEN** an admin navigates to `/settings/*` on a viewport with `max-width: 639px`
- **THEN** the page SHALL render a section picker dropdown above the content area showing the current section's label and a chevron
- **AND** the left-hand sidebar SHALL be hidden
- **AND** content SHALL fill the available width

#### Scenario: Dropdown navigates between sections
- **WHEN** the section picker dropdown is open
- **AND** the user selects a section other than the current one
- **THEN** the page SHALL navigate to that section's route (e.g. `/settings/profiles`)
- **AND** the dropdown SHALL close

#### Scenario: Active section reflected in dropdown closed state
- **WHEN** the page renders with the dropdown visible and route `/settings/profiles`
- **THEN** the dropdown's closed-state label SHALL read "Task Profiles"

### Requirement: Section picker keyboard navigation

The section picker dropdown SHALL be keyboard-operable. The trigger button SHALL toggle the panel via Enter or Space. While open, ArrowDown/ArrowUp SHALL move focus among options, Enter SHALL select, and Escape SHALL close without selecting. The trigger SHALL expose `aria-expanded` reflecting open state, and the panel SHALL use a listbox role.

#### Scenario: Open with Enter and select with Enter
- **WHEN** focus is on the picker trigger and the user presses Enter
- **THEN** the panel SHALL open with focus moved to the option matching the active route (or the first option if no route is active)
- **AND** subsequent ArrowDown SHALL move focus down the list
- **AND** Enter on a focused option SHALL navigate to that section's route and close the panel
- **AND** focus SHALL return to the trigger button after the panel closes

#### Scenario: Open with ArrowDown focuses the first option
- **WHEN** focus is on the picker trigger and the user presses ArrowDown
- **THEN** the panel SHALL open with focus moved to the first option

#### Scenario: Escape closes without selecting
- **WHEN** the panel is open and the user presses Escape
- **THEN** the panel SHALL close
- **AND** the active route SHALL NOT change

### Requirement: Per-role timeout inputs adjacent to model selectors
The Task Management page's "LLM Models" section SHALL render three model groups — "Title generation", "Default task processing", and "Transcription" — and each group SHALL include both its model selector and a timeout input rendered immediately below the selector. Each timeout input SHALL be a number input with `min=1`, integer step, and a "seconds" suffix label. Each input SHALL bind to its respective settings key:

| Group | Settings key |
|---|---|
| Title generation | `title_generation_timeout` |
| Default task processing | `task_processing_timeout` |
| Transcription | `transcription_timeout` |

When the page is saved, the frontend SHALL include all three timeout values in the `PUT /api/settings` payload alongside the model selections. The previous standalone generic "LLM Timeout" input SHALL be removed from the page.

#### Scenario: Three timeout inputs render adjacent to model selectors
- **WHEN** an admin navigates to `/settings/tasks`
- **THEN** the "LLM Models" section displays three groups, each with a model selector and a timeout input directly below it

#### Scenario: Saving sends all three timeout values
- **WHEN** an admin sets the title timeout to 20, the task processing timeout to 180, and the transcription timeout to 45 and clicks Save
- **THEN** the frontend sends `PUT /api/settings` with `title_generation_timeout: 20`, `task_processing_timeout: 180`, and `transcription_timeout: 45`

#### Scenario: Defaults shown when no settings exist
- **WHEN** an admin loads the page and none of the three timeout settings exist in the database
- **THEN** all three timeout inputs display `30`

#### Scenario: Legacy generic input removed
- **WHEN** an admin navigates to `/settings/tasks`
- **THEN** no standalone "LLM Timeout" input exists outside the per-model groups

