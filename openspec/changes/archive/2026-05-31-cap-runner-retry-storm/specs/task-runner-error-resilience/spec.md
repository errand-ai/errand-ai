## ADDED Requirements

### Requirement: execute_command detects Google's raw 401 in addition to UNAUTHENTICATED

The task-runner's `execute_command` wrapper in `task-runner/main.py` SHALL trigger the transparent Google Workspace token refresh path on either of:

1. The existing substring `"status": "UNAUTHENTICATED"` anywhere in the combined stdout+stderr output (current behaviour), OR
2. The conjunction of `"code": 401` AND `"Request had invalid authentication credentials"` anywhere in the combined output (Google's raw API 401 shape).

When either condition matches, the wrapper SHALL proceed exactly as the existing path: call `POST ${ERRAND_API_URL}/api/google/refresh-token`, mutate `os.environ["GOOGLE_WORKSPACE_CLI_TOKEN"]` with the new token, emit a `token_refreshed` event to the transcript, and re-run the same command once. The existing one-retry-per-invocation cap, the module-level refresh lock, and the rest of the recovery flow SHALL be unchanged.

The detection SHALL be case-sensitive and SHALL match the substrings as literals, not regular expressions, to mirror the existing implementation style and avoid false positives from arbitrary CLI output.

#### Scenario: gws CLI returns Google's raw 401 and refresh fires

- **WHEN** `execute_command` runs a `gws drive files list` invocation and the combined output contains `"code": 401` and `"Request had invalid authentication credentials"`
- **THEN** the wrapper calls the errand server's `/api/google/refresh-token` endpoint, updates the `GOOGLE_WORKSPACE_CLI_TOKEN` environment variable, emits a `token_refreshed` event, and re-runs the same command exactly once

#### Scenario: Legacy UNAUTHENTICATED path unchanged

- **WHEN** a tool emits the substring `"status": "UNAUTHENTICATED"` in its output
- **THEN** the wrapper triggers token refresh as it does today; the new 401-detection clause is not consulted (either condition is sufficient)

#### Scenario: Partial match does not trigger refresh

- **WHEN** the combined output contains `"code": 401` but not the `"Request had invalid authentication credentials"` substring (e.g. an unrelated CLI returning a 401 with a different message)
- **THEN** the wrapper does NOT trigger token refresh; the conjunction is required, not just the code

#### Scenario: Refresh cap still applies under the new detection

- **WHEN** `execute_command` detects Google's raw 401, refreshes the token, re-runs the command, and the rerun also returns a raw 401
- **THEN** the wrapper does NOT refresh a second time within the same invocation; the existing one-retry-per-invocation cap is honoured and the failure is surfaced
