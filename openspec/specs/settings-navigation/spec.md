## Requirements

### Requirement: Cloud Service navigation link
The Settings sidebar navigation SHALL include a "Cloud Service" link.

#### Scenario: Sidebar displays Cloud Service link
- **WHEN** an admin navigates to any settings sub-page
- **THEN** the sidebar SHALL display a "Cloud Service" link pointing to `/settings/cloud`
- **AND** the link SHALL appear after "Task Generators" and before "User Management" in the navigation order

### Requirement: Task Generators navigation link
The Settings sidebar navigation SHALL include a "Task Generators" link pointing to `/settings/task-generators`.

#### Scenario: Sidebar displays Task Generators link
- **WHEN** an admin navigates to any settings sub-page
- **THEN** the sidebar SHALL display a "Task Generators" link pointing to `/settings/task-generators`
- **AND** the link SHALL appear after "Integrations" in the navigation order
