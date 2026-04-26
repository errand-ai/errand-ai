## 1. Database Model and Migration

- [x] 1.1 Add `include_git_skills` Boolean column (not null, server_default=true) to `TaskProfile` in `errand/models.py`
- [x] 1.2 Create Alembic migration to add the `include_git_skills` column to the `task_profiles` table

## 2. Backend API

- [x] 2.1 Update the profile CRUD endpoints in `errand/main.py` to accept and return the `include_git_skills` field
- [x] 2.2 Update the profile resolution in `errand/task_manager.py` to pass `include_git_skills` through as `_profile_include_git_skills`

## 3. Worker Skill Filtering

- [x] 3.1 Fix the skill filtering logic in `errand/task_manager.py` to handle git-sourced skills separately from DB skills — when `profile_skill_ids` is not null, filter DB skills by UUID and include/exclude git skills based on `_profile_include_git_skills`

## 4. Frontend

- [x] 4.1 Add an "Include Git Repository Skills" checkbox to the task profile form in `TaskProfilesPage.vue`, visible when skill mode is "Select specific" or "None"
- [x] 4.2 Wire the checkbox to read/write the `include_git_skills` field on the profile payload
- [x] 4.3 Update the profile summary display to show git skills inclusion status when skills are explicitly configured

## 5. Testing

- [x] 5.1 Add/update backend tests for the new `include_git_skills` field in profile CRUD operations
- [x] 5.2 Add/update worker tests for the fixed skill filtering logic (DB skills by UUID, git skills by flag)
- [x] 5.3 Add/update frontend tests for the git skills checkbox behaviour
- [x] 5.4 Run the full test suite (backend + frontend) to verify no regressions
