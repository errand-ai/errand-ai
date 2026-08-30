## ADDED Requirements

### Requirement: Log streaming completes only when the pod terminates

A runtime's log-streaming method SHALL NOT treat the end of the pod log stream as evidence that the pod finished. When the stream ends, the runtime SHALL read the pod's phase. Only a terminal phase (`Succeeded` or `Failed`) SHALL end the stream; while the pod is still running, the runtime SHALL resume streaming and continue yielding lines.

A resumed stream SHALL request only log content produced after the last line already yielded, so that a resume neither repeats nor loses output.

Resumption SHALL be bounded by pod state rather than by attempt count alone: it continues while the pod runs and stops when the pod terminates or can no longer be read. A bounded backstop MAY additionally limit resumption to guard against a pathological loop, but SHALL NOT be the primary termination condition.

The runtime SHALL distinguish, internally and in its logs, a stream that ended because the pod terminated from one that ended while the pod was still running. The two SHALL NOT be signalled identically.

#### Scenario: Stream ends while the pod is still running

- **WHEN** the pod log stream ends and the pod's phase is neither `Succeeded` nor `Failed`
- **THEN** the runtime resumes streaming instead of completing
- **AND** it records that the stream was interrupted and is being resumed

#### Scenario: Stream ends because the pod finished

- **WHEN** the pod log stream ends and the pod has reached a terminal phase
- **THEN** the runtime completes normally

#### Scenario: A resumed stream is continuous

- **WHEN** a stream is interrupted and resumed
- **THEN** the lines yielded across the interruption contain no duplicate of a line already yielded
- **AND** no line produced by the pod between the interruption and the resume is omitted

#### Scenario: Interruption is not silent

- **WHEN** a stream ends early and is resumed
- **THEN** the event is logged, naming the pod and that the pod was still running

### Requirement: A running container is never destroyed on an unknown exit code

A runtime SHALL NOT delete a Job or otherwise destroy a container whose exit code could not be determined while that container is still running. Where the exit code is unknown, the runtime SHALL establish whether the container has terminated before any cleanup, and SHALL leave a still-running container in place.

#### Scenario: Cleanup is withheld from a running container

- **WHEN** cleanup would run for a task whose exit code is unknown
- **AND** the pod's container is still running
- **THEN** the Job is not deleted
- **AND** the condition is logged

#### Scenario: Cleanup proceeds for a terminated container

- **WHEN** the container has terminated
- **THEN** cleanup deletes the Job and its associated resources as before

#### Scenario: An abandoned pod is still reclaimed

- **WHEN** a container is left in place because it was still running
- **THEN** it remains subject to the Job's `ttlSecondsAfterFinished` and to orphaned-Job recovery, so it is not leaked indefinitely
