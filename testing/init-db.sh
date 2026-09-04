#!/bin/bash
set -e

# Runs once, on an empty data directory, before anything connects.
#
# Hindsight shares this database and keeps its tables in a `hindsight` schema,
# which it creates and migrates itself.
#
# Both extensions are created here, as superuser, in the **default (public)
# schema** — and for `pg_trgm` that placement is a fix, not a convenience.
#
# Hindsight keeps its tables in its own schema but resolves operators against a
# search_path that has `public` on it, so both extensions have to live there:
#
#   * `vector` — Hindsight insists on `public` itself. Created anywhere else, its
#     migration logs "pgvector extension found in schema 'hindsight' instead of
#     'public'. Attempting to relocate..." and moves it on every fresh start.
#   * `pg_trgm` — left to itself, Hindsight's own migration creates this one in
#     its tenant schema, where its runtime then cannot resolve the `%` operator.
#     Every retain fails in entity resolution with
#     `operator does not exist: text % text` and retries on a one-minute backoff
#     forever; the MCP `retain` call still returns "accepted", so the only
#     symptom is that memory silently never appears. Reproduced on a fresh
#     volume, and fixed by this line.
#
# The fix works because `CREATE EXTENSION IF NOT EXISTS` matches on the
# *database*, not the schema: creating it here first means Hindsight's own
# mis-placed create becomes a no-op. That same rule is why getting the schema
# wrong here would be worse than doing nothing.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
EOSQL
