## ADDED Requirements

### Requirement: Container runtimes return pod logs as decoded text

A runtime's `result()` SHALL return logs as decoded text with real line-break characters. It SHALL NOT return the `repr` of a bytes object, and SHALL NOT return a value in which line breaks are the two-character sequence backslash-`n`.

`KubernetesRuntime` SHALL read pod logs with `_preload_content=False` and decode the response itself, as its streaming path already does. It SHALL NOT rely on the Kubernetes client's preloaded `str` deserialisation, which returns `str(bytes)` — the bytes repr — whenever the response body is not valid JSON, as pod logs never are.

The logs a runtime returns for a completed task SHALL be byte-equivalent in form to what its streaming path yields for the same task, so that a consumer splitting on line breaks and parsing each line as JSON obtains the same events from both.

#### Scenario: Completed-task logs contain real line breaks

- **WHEN** `result()` returns logs for a task whose pod emitted multiple lines
- **THEN** the returned string contains real line-break characters
- **AND** it does not begin with `b'` or `b"`
- **AND** it contains no literal backslash-`n` sequences introduced in place of line breaks

#### Scenario: Each stored log line is independently parseable

- **WHEN** logs returned by `result()` are split on line breaks
- **THEN** a line the task-runner emitted as a JSON event parses as a JSON object exposing `type`
- **AND** it is not necessary to parse the whole log as a single value to reach it

#### Scenario: Stored and streamed logs agree

- **WHEN** the same task's logs are obtained from the streaming path and from `result()`
- **THEN** both yield the same sequence of task-runner event lines

#### Scenario: Pod logs are read without client-side deserialisation

- **WHEN** `KubernetesRuntime` reads pod logs for a completed task
- **THEN** the read passes `_preload_content=False`
- **AND** the runtime decodes the response itself rather than accepting a client-deserialised `str`

### Requirement: Existing bytes-repr logs are repaired

Task logs already stored as a bytes repr SHALL be repaired to their decoded text, so the fix applies to tasks created before it as well as after.

A stored value SHALL be treated as corrupt only when every one of the following holds: it begins with `b'` or `b"`, it ends with the matching quote, it contains no real line-break characters, and evaluating it as a Python literal yields a `bytes` object. A value failing any of these SHALL be left unchanged.

A value that cannot be decoded cleanly SHALL be left unchanged rather than partially rewritten.

#### Scenario: A corrupt log is repaired

- **WHEN** a stored log satisfies every corruption condition
- **THEN** it is replaced by the decoded text of the bytes literal it represents
- **AND** the repaired value contains real line breaks

#### Scenario: A healthy log is untouched

- **WHEN** a stored log contains real line breaks
- **THEN** it is left byte-for-byte unchanged, whatever it begins with

#### Scenario: An ambiguous value is left alone

- **WHEN** a stored log begins with `b'` but does not evaluate to a `bytes` literal — for example because it was truncated before its closing quote
- **THEN** it is left unchanged
- **AND** the repair is reported as skipped rather than reported as applied
