## Purpose

New `profile_select` field type in the platform credential form for dynamically selecting a task profile when configuring the email platform.

## ADDED Requirements

### Requirement: profile_select field type

The `PlatformCredentialForm` component SHALL support a `profile_select` field type. When a credential schema field has `"type": "profile_select"`, the form SHALL fetch the list of task profiles from `GET /api/profiles` and render a `<select>` dropdown populated with profile names. The selected value SHALL be the profile ID (UUID).

#### Scenario: Profile dropdown renders

- **WHEN** the email platform credential form is displayed and there are 3 task profiles configured
- **THEN** a dropdown appears for the "Task Profile" field with 3 options

#### Scenario: Profile selection saved

- **WHEN** an admin selects a profile from the dropdown and clicks "Test & Save"
- **THEN** the saved credentials include `email_profile` set to the selected profile's ID

#### Scenario: No profiles available

- **WHEN** the email platform credential form is displayed and no task profiles exist
- **THEN** the dropdown is empty and the form indicates that a task profile must be created first

### Requirement: Profile dropdown fetches from API

The `profile_select` field SHALL fetch profiles from the existing `GET /api/profiles` endpoint on mount. The dropdown options SHALL display the profile `name` as the label and the profile `id` as the value.

#### Scenario: Profiles loaded on mount

- **WHEN** the credential form mounts with a `profile_select` field
- **THEN** it fetches profiles from `GET /api/profiles` and populates the dropdown
