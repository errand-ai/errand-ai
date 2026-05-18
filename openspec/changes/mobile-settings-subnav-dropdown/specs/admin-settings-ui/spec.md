## MODIFIED Requirements

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
