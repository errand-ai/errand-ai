## ADDED Requirements

### Requirement: Settings sidebar navigation
The Settings page SHALL display a sidebar navigation on the left side of the page content. The sidebar SHALL contain four navigation links: "Agent Configuration" (`/settings/agent`), "Task Management" (`/settings/tasks`), "Security" (`/settings/security`), and "Integrations" (`/settings/integrations`). Each link SHALL use `<router-link>` for client-side navigation. The active link SHALL be highlighted with `bg-gray-100 text-gray-900 font-medium rounded-md` styling. Inactive links SHALL use `text-gray-600` with `hover:text-gray-900 hover:bg-gray-50`. The sidebar SHALL have a fixed width of approximately 200px and SHALL be sticky-positioned so it remains visible while scrolling the content area.

#### Scenario: Sidebar displays all navigation items
- **WHEN** an admin navigates to any settings sub-page
- **THEN** the sidebar displays four links: "Agent Configuration", "Task Management", "Security", "Integrations"

#### Scenario: Active sub-page is highlighted
- **WHEN** an admin is on the Agent Configuration sub-page (`/settings/agent`)
- **THEN** the "Agent Configuration" sidebar link has the active highlight style and other links have inactive styling

#### Scenario: Clicking sidebar link navigates to sub-page
- **WHEN** an admin clicks "Security" in the sidebar
- **THEN** the browser navigates to `/settings/security` and the Security sub-page content is displayed

#### Scenario: Sidebar remains visible while scrolling
- **WHEN** an admin scrolls down on a settings sub-page with long content
- **THEN** the sidebar remains visible in its fixed position

### Requirement: Settings sub-page layout
The Settings page SHALL use a two-column layout with the sidebar navigation on the left and a `<router-view>` on the right for rendering the active sub-page. The "Settings" heading SHALL remain at the top of the page above both columns. The content area SHALL fill the remaining width after the sidebar.

#### Scenario: Layout structure
- **WHEN** an admin navigates to any settings sub-page
- **THEN** the page displays the "Settings" heading at the top, with a sidebar on the left and the sub-page content on the right

### Requirement: Unsaved changes warning on sub-page switch
When the active sub-page has unsaved changes and the admin clicks a different sidebar link, a browser confirmation dialog SHALL appear warning about unsaved changes. If the admin confirms, the navigation proceeds and unsaved changes are discarded. If the admin cancels, the navigation is prevented and the current sub-page remains active.

#### Scenario: Warning shown when switching with unsaved changes
- **WHEN** the admin has unsaved changes on the Agent Configuration sub-page and clicks "Security" in the sidebar
- **THEN** a confirmation dialog appears warning about unsaved changes

#### Scenario: Navigation proceeds on confirm
- **WHEN** the unsaved changes dialog appears and the admin confirms
- **THEN** the browser navigates to the clicked sub-page and unsaved changes are discarded

#### Scenario: Navigation prevented on cancel
- **WHEN** the unsaved changes dialog appears and the admin cancels
- **THEN** the current sub-page remains active and unsaved changes are preserved
