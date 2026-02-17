## Requirements

### Requirement: Persistent header navigation bar
The App.vue header SHALL display a horizontal navigation bar between the logo/title and the user controls. The navigation SHALL contain links for "Board" (`/`), "Archived" (`/archived`), and "Settings" (`/settings`). The "Settings" link SHALL only be visible when `auth.isAdmin` is true. The currently active route SHALL be visually indicated with a pill-style highlight (`bg-gray-100 text-gray-900 rounded-md`). Inactive links SHALL use `text-gray-600` with `hover:text-gray-900 hover:bg-gray-50`. The "Settings" link SHALL be highlighted as active when the current route starts with `/settings` (matching any sub-page).

#### Scenario: Navigation visible on Kanban board
- **WHEN** an authenticated user views the Kanban board at `/`
- **THEN** the header displays "Board" (highlighted as active), "Archived", and "Settings" (if admin) navigation links between the logo and user controls

#### Scenario: Navigation visible on Archived page
- **WHEN** an authenticated user navigates to `/archived`
- **THEN** the header displays "Board", "Archived" (highlighted as active), and "Settings" (if admin) navigation links

#### Scenario: Navigation visible on Settings page
- **WHEN** an admin user navigates to `/settings/agent`
- **THEN** the header displays "Board", "Archived", and "Settings" (highlighted as active) navigation links

#### Scenario: Settings link active on any settings sub-page
- **WHEN** an admin user navigates to `/settings/security`
- **THEN** the "Settings" link in the header navigation is highlighted as active

#### Scenario: Settings link hidden for non-admin
- **WHEN** a non-admin authenticated user views any page
- **THEN** the navigation bar shows "Board" and "Archived" but not "Settings"

### Requirement: Settings nested routing
The Vue Router SHALL define `/settings` as a parent route with four child routes: `/settings/agent` (Agent Configuration), `/settings/tasks` (Task Management), `/settings/security` (Security), and `/settings/integrations` (Integrations). Navigating to `/settings` SHALL redirect to `/settings/agent`. All child routes SHALL inherit the admin role guard from the parent route. Each child route SHALL render its corresponding sub-page component within the `SettingsPage.vue` layout's `<router-view>`.

#### Scenario: Default settings redirect
- **WHEN** an admin navigates to `/settings`
- **THEN** the browser redirects to `/settings/agent`

#### Scenario: Direct sub-page navigation
- **WHEN** an admin navigates directly to `/settings/security`
- **THEN** the Security sub-page is rendered within the settings layout

#### Scenario: Admin guard on child routes
- **WHEN** a non-admin user navigates to `/settings/tasks`
- **THEN** the user is redirected to `/`

#### Scenario: Unknown settings sub-page
- **WHEN** an admin navigates to `/settings/nonexistent`
- **THEN** the browser redirects to `/settings/agent`

### Requirement: User dropdown contains only session actions
The user dropdown menu SHALL contain only the username display and a "Log out" button. Navigation items ("Archived Tasks", "Settings") SHALL be removed from the dropdown. The dropdown trigger SHALL continue to show the user's display name with a chevron icon.

#### Scenario: Dropdown contains only Log out
- **WHEN** an authenticated user clicks the username in the header
- **THEN** the dropdown shows only a "Log out" option

#### Scenario: Archived Tasks removed from dropdown
- **WHEN** an authenticated user opens the user dropdown
- **THEN** there is no "Archived Tasks" option in the dropdown
