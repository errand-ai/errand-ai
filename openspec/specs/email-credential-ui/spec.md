## Purpose

`profile_select` field type in the platform credential form for dynamically selecting a task profile. Available for any platform credential schema, though no longer used by the email platform (email task generation settings moved to Task Generators page).

## Requirements

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

### Requirement: Profile dropdown fetches from API

The `profile_select` field SHALL fetch profiles from the existing `GET /api/profiles` endpoint on mount. The dropdown options SHALL display the profile `name` as the label and the profile `id` as the value.

#### Scenario: Profiles loaded on mount

- **WHEN** the credential form mounts with a `profile_select` field
- **THEN** it fetches profiles from `GET /api/profiles` and populates the dropdown
