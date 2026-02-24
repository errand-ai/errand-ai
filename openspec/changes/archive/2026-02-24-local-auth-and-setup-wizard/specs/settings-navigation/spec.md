## MODIFIED Requirements

### Requirement: Settings sidebar navigation
The Settings page SHALL display a sidebar navigation on the left side of the page content. The sidebar SHALL contain five navigation links: "Agent Configuration" (`/settings/agent`), "Task Management" (`/settings/tasks`), "Security" (`/settings/security`), "Integrations" (`/settings/integrations`), and "User Management" (`/settings/users`). Each link SHALL use `<router-link>` for client-side navigation. The active link SHALL be highlighted with `bg-gray-100 text-gray-900 font-medium rounded-md` styling. Inactive links SHALL use `text-gray-600` with `hover:text-gray-900 hover:bg-gray-50`. The sidebar SHALL have a fixed width of approximately 200px and SHALL be sticky-positioned so it remains visible while scrolling the content area.

#### Scenario: Sidebar displays all navigation items
- **WHEN** an admin navigates to any settings sub-page
- **THEN** the sidebar displays five links: "Agent Configuration", "Task Management", "Security", "Integrations", "User Management"

#### Scenario: Active sub-page is highlighted
- **WHEN** an admin is on the User Management sub-page (`/settings/users`)
- **THEN** the "User Management" sidebar link has the active highlight style and other links have inactive styling

#### Scenario: Clicking sidebar link navigates to sub-page
- **WHEN** an admin clicks "User Management" in the sidebar
- **THEN** the browser navigates to `/settings/users` and the User Management sub-page content is displayed
