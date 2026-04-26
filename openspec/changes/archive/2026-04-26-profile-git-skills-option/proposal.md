## Why

When a task profile uses "select specific" skills mode, the skill picker only shows database-managed skills (which have UUIDs). Git-sourced skills are silently excluded because the profile filter (`skill_ids`) matches on UUID and git skills don't have one. This means any profile with explicit skill selection loses access to all git repository skills, with no way to include them. Users expect to be able to include or exclude the git skills repository as a unit alongside specific managed skills.

## What Changes

- Add an `include_git_skills` boolean field to the TaskProfile model, defaulting to `true` (preserving current "inherit all" behaviour for existing profiles)
- Update the frontend task profile form to show a toggle/checkbox for "Include Git Repository Skills" when the skill mode is "select specific"
- Update the worker's skill filtering logic to respect the new flag: when `include_git_skills` is true, git-sourced skills are merged into the skill set alongside any selected managed skills; when false, they are excluded
- Fix the existing filter bug where git skills are always excluded in "select specific" mode because they lack a UUID

## Capabilities

### New Capabilities

(none)

### Modified Capabilities
- `task-profile-worker-resolution`: The skill filtering logic needs to handle git-sourced skills separately from managed skills, using the new `include_git_skills` flag
- `task-profile-settings-ui`: The profile form needs a toggle for including/excluding git repository skills when skill mode is "select specific"
- `task-profile-model`: The TaskProfile model needs an `include_git_skills` column

## Impact

- **errand/models.py**: Add `include_git_skills` Boolean column to TaskProfile
- **errand/alembic/**: New migration to add the column
- **errand/task_manager.py**: Update skill filtering to check `include_git_skills` flag and stop filtering out git skills by UUID mismatch
- **frontend/src/pages/settings/TaskProfilesPage.vue**: Add git skills toggle to the profile form
- **errand/main.py**: Pass `include_git_skills` through profile resolution
- **Existing profiles**: No breaking change — `include_git_skills` defaults to `true`, so existing "inherit" profiles continue to include everything and existing "select specific" profiles gain git skills (fixing the current silent exclusion bug)
