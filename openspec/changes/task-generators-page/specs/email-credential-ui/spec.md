## MODIFIED Requirements

### Requirement: profile_select field type
The `PlatformCredentialForm` component SHALL support a `profile_select` field type. When a credential schema field has `"type": "profile_select"`, the form SHALL fetch the list of task profiles from `GET /api/profiles` and render a `<select>` dropdown populated with profile names. The selected value SHALL be the profile ID (UUID).

This field type is no longer used in the email credential schema but remains available for other platform credential forms and the Task Generators page.

#### Scenario: Profile dropdown renders
- **WHEN** a platform credential form with a `profile_select` field is displayed and there are 3 task profiles configured
- **THEN** a dropdown appears with 3 options

#### Scenario: Profile selection saved
- **WHEN** an admin selects a profile from the dropdown and saves
- **THEN** the saved data includes the field set to the selected profile's ID

#### Scenario: No profiles available
- **WHEN** a form with a `profile_select` field is displayed and no task profiles exist
- **THEN** the dropdown is empty and the form indicates that a task profile must be created first

## REMOVED Requirements

### Requirement: Email credential includes task profile and poll interval
**Reason**: Task generation settings (profile, poll interval) have been moved to the new Task Generators settings page. Email credentials now only contain connection-related settings (IMAP/SMTP server details, security, username, password, authorized recipients).
**Migration**: Existing `email_profile` and `poll_interval` values are migrated to a `task_generator` record with `type="email"` via database migration.
