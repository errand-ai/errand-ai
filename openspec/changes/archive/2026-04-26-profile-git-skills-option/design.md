## Context

Task profiles allow users to select which skills are available via a three-state `skill_ids` field: null (inherit all), empty array (none), or explicit UUIDs (select specific). The "select specific" mode only works for DB-managed skills because it filters by UUID. Git-sourced skills have no UUID and are silently excluded whenever a profile has an explicit `skill_ids` list. There is no way to include git-sourced skills in a profile with selective skill configuration.

## Goals / Non-Goals

**Goals:**
- Users can include or exclude git repository skills as a unit when configuring a task profile
- The existing "inherit all" behaviour continues to include both DB and git skills
- The fix is backwards-compatible with existing profiles

**Non-Goals:**
- Selecting individual git skills (they are managed as a repository, not individually)
- Changing how the git skills repository is configured (that stays in Agent Configuration)

## Decisions

### D1: Add `include_git_skills` Boolean column with default true

**Decision**: Add a `include_git_skills` Boolean column to TaskProfile, defaulting to `true`. When `skill_ids` is explicit (select specific mode), this flag controls whether git-sourced skills are merged in alongside the selected DB skills.

**Alternatives considered**:
- *Adding git skills to skill_ids with synthetic IDs*: Would require generating stable IDs for git skills and keeping them in sync across refreshes. Fragile and complex.
- *A separate `git_skills` JSON field with individual git skill names*: Over-engineered for a repository that's managed as a unit. Users configure the repository, not individual git skills.

**Rationale**: Git skills are configured as a repository-level setting (URL + branch + path). The natural granularity for profile control is "include the whole repo or not". A simple Boolean matches this granularity cleanly.

### D2: Three-state interaction with skill_ids

**Decision**: The `include_git_skills` flag is only meaningful when `skill_ids` is not null (i.e., when the profile is in "select specific" or "none" mode). When `skill_ids` is null (inherit), all skills including git skills are inherited regardless of the flag.

| skill_ids | include_git_skills | Result |
|-----------|-------------------|--------|
| null (inherit) | ignored | All DB + all git skills |
| [] (none) | false | No skills at all |
| [] (none) | true | Git skills only |
| [uuid1, uuid2] | false | Only those 2 DB skills |
| [uuid1, uuid2] | true | Those 2 DB skills + all git skills |

### D3: Frontend shows toggle only in "select specific" mode

**Decision**: The "Include Git Repository Skills" checkbox appears in the profile form only when the skill mode is "Select specific" or "None". In "Inherit from default" mode, the toggle is hidden since all skills are included anyway.

## Risks / Trade-offs

**[Risk] Existing profiles with "select specific" gain git skills** → Since `include_git_skills` defaults to `true`, existing profiles that previously (accidentally) excluded git skills will now include them. This is the desired fix — the previous exclusion was a bug, not intentional behaviour.
