## MODIFIED Requirements

### Requirement: Display current user identity
The frontend SHALL display the authenticated user's name or email in the app header, derived from the access token claims. For admin users, the name SHALL be displayed as a clickable dropdown trigger. For non-admin users, the name SHALL be displayed as static text (unchanged from current behavior).

#### Scenario: Admin user identity shown with dropdown
- **WHEN** an admin user is authenticated
- **THEN** the app header displays the user's name as a clickable element that opens a dropdown menu

#### Scenario: Non-admin user identity shown
- **WHEN** a non-admin user is authenticated
- **THEN** the app header displays the user's name as static text

### Requirement: Logout button in header
The frontend SHALL provide a logout action in the app header. For non-admin users, the logout button SHALL be displayed as a standalone button (unchanged from current behavior). For admin users, the logout action SHALL be available as an item in the admin dropdown menu.

#### Scenario: Non-admin user clicks logout
- **WHEN** a non-admin user clicks the logout button
- **THEN** the browser navigates to `/auth/logout`

#### Scenario: Admin user clicks logout in dropdown
- **WHEN** an admin user opens the dropdown and clicks "Log out"
- **THEN** the browser navigates to `/auth/logout`

## ADDED Requirements

### Requirement: Admin dropdown menu
The app header SHALL display a dropdown menu for admin users. The dropdown SHALL be triggered by clicking the user's display name. The dropdown SHALL contain two items: "Settings" (linking to `/settings`) and "Log out" (triggering the logout action). The dropdown SHALL close when clicking outside of it.

#### Scenario: Admin opens dropdown
- **WHEN** an admin user clicks their display name in the header
- **THEN** a dropdown menu appears with "Settings" and "Log out" options

#### Scenario: Admin clicks Settings
- **WHEN** an admin user clicks "Settings" in the dropdown
- **THEN** the app navigates to `/settings`

#### Scenario: Admin clicks Log out
- **WHEN** an admin user clicks "Log out" in the dropdown
- **THEN** the browser navigates to `/auth/logout`

#### Scenario: Dropdown closes on outside click
- **WHEN** the dropdown is open and the user clicks outside of it
- **THEN** the dropdown closes

#### Scenario: Non-admin user sees no dropdown
- **WHEN** a non-admin user is authenticated
- **THEN** no dropdown menu is displayed in the header
