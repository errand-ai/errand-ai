## MODIFIED Requirements

### Requirement: Settings nested routing
The Vue Router SHALL define `/settings` as a parent route with five child routes: `/settings/agent` (Agent Configuration), `/settings/tasks` (Task Management), `/settings/security` (Security), `/settings/integrations` (Integrations), and `/settings/users` (User Management). Navigating to `/settings` SHALL redirect to `/settings/agent`. All child routes SHALL inherit the admin role guard from the parent route. Each child route SHALL render its corresponding sub-page component within the `SettingsPage.vue` layout's `<router-view>`.

#### Scenario: Default settings redirect
- **WHEN** an admin navigates to `/settings`
- **THEN** the browser redirects to `/settings/agent`

#### Scenario: User Management sub-page navigation
- **WHEN** an admin navigates to `/settings/users`
- **THEN** the User Management sub-page is rendered within the settings layout

#### Scenario: Admin guard on child routes
- **WHEN** a non-admin user navigates to `/settings/users`
- **THEN** the user is redirected to `/`
