## ADDED Requirements

### Requirement: Profile model setting mirrors `model` and `model_id` on write

`POST /api/task-profiles` and `PUT /api/task-profiles/{id}` SHALL normalise the `model` field so that, when it is an object carrying a model name under either `model` or `model_id`, both keys are present and equal in the stored value. The backend resolves against `model`; the shared profile editor card reads and writes `model_id`. Mirroring on write lets each side find the selection regardless of which wrote it, matching the existing behaviour of `PUT /api/settings` for model settings.

A `model` that is null, a plain string, or an object carrying neither key SHALL be stored unchanged.

#### Scenario: Editor-shaped object gains the canonical key

- **WHEN** an admin creates a profile with `model: {"provider_id": "p1", "model_id": "claude-haiku-4-5-20251001"}`
- **THEN** the stored value carries `model: "claude-haiku-4-5-20251001"` alongside the original `model_id` and `provider_id`

#### Scenario: Legacy-shaped object gains the mirror key

- **WHEN** an admin creates a profile with `model: {"provider_id": null, "model": "legacy-model"}`
- **THEN** the stored value carries `model_id: "legacy-model"` alongside `model`, so the editor card displays the selection

#### Scenario: Update mirrors the same way

- **WHEN** an admin updates a profile with `model: {"provider_id": "p2", "model_id": "claude-sonnet-4-5-20250929"}`
- **THEN** the stored value carries both `model` and `model_id` set to `claude-sonnet-4-5-20250929`

#### Scenario: Cleared model stays null

- **WHEN** an admin updates a profile with `model: null`
- **THEN** the stored value is `null` and the profile inherits the global model

#### Scenario: Plain string model is unchanged

- **WHEN** an admin creates a profile with `model: "claude-haiku-4-5-20251001"`
- **THEN** the stored value is the string unchanged
