## ADDED Requirements

### Requirement: Task runner pushes result via callback before exiting

The task runner SHALL, after generating structured output and printing it to stdout, attempt to POST the output JSON to a callback URL if configured. The task runner SHALL read `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` from environment variables. If both are set, the task runner SHALL send an HTTP POST to `RESULT_CALLBACK_URL` with the output JSON as the request body, `Content-Type: application/json`, and `Authorization: Bearer <RESULT_CALLBACK_TOKEN>` headers, using a 10-second timeout. If the POST succeeds (HTTP 200), the task runner SHALL log success. If the POST fails (network error, non-200 status, timeout), the task runner SHALL log a warning and continue. If either environment variable is missing, the task runner SHALL skip the callback silently and continue — stdout output and `/output/result.json` file output SHALL still be written as fallbacks. The callback POST SHALL never cause the task runner to exit with an error code.

#### Scenario: Callback POST succeeds

- **WHEN** the task runner completes with structured output and `RESULT_CALLBACK_URL` and `RESULT_CALLBACK_TOKEN` are set, and the backend responds with HTTP 200
- **THEN** the task runner logs success, writes output to stdout, writes to `/output/result.json`, and exits with code 0

#### Scenario: Callback POST fails gracefully

- **WHEN** the task runner completes with structured output and the callback POST returns a non-200 status or times out
- **THEN** the task runner logs a warning, still writes output to stdout and `/output/result.json`, and exits with code 0

#### Scenario: Callback not configured

- **WHEN** the task runner completes with structured output and `RESULT_CALLBACK_URL` is not set
- **THEN** the task runner skips the callback POST silently and continues with stdout and file output as before

#### Scenario: Callback POST network error

- **WHEN** the task runner attempts to POST the result and the backend is unreachable (connection refused, DNS failure)
- **THEN** the task runner logs a warning and exits with code 0 (output still written to stdout and file)
