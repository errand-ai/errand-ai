## Context

`parse_interval` uses a strict regex `(\d+)([mhdw])` that only matches compact formats like `7d`. LLM agents calling `schedule_task` produce natural variants like `7 days`, `2 hours`, `weekly`. The failure is silent — bad intervals are stored, and rescheduling fails a week later with a warning log.

## Goals / Non-Goals

**Goals:**
- `parse_interval` accepts both compact (`7d`) and human-readable (`7 days`) formats
- `schedule_task` validates `repeat_interval` at write time and returns a clear error if unparseable
- `schedule_task` tool description documents the accepted formats

**Non-Goals:**
- Supporting crontab expressions (out of scope, noted in existing spec)
- Changing the stored format in the database (we normalise to compact before storing)

## Decisions

### Decision 1: Normalise inside parse_interval

Add a normalisation step at the top of `parse_interval` that converts common human-readable patterns to compact format before applying the existing regex. This fixes both new and existing tasks with bad formats.

Normalisation rules:
- Strip and lowercase the input
- Map word units to compact: `minutes?` → `m`, `hours?` → `h`, `days?` → `d`, `weeks?` → `w`
- Map named intervals: `daily` → `1d`, `weekly` → `1w`, `hourly` → `1h`
- Handle spaces between number and unit: `7 days` → `7d`

### Decision 2: Validate at schedule_task write time

Call `parse_interval` in `schedule_task` before storing. If it returns None, return an error to the caller. Store the normalised compact form, not the raw input.

### Decision 3: Improve tool description

Add format examples to the `schedule_task` docstring so LLMs know the expected format upfront.

## Risks / Trade-offs

- **Risk**: Normalisation could match unintended patterns. **Mitigation**: The normalisation only handles well-known duration words, then still validates through the existing regex.
