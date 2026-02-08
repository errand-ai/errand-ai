# Code Style and Conventions

## Python (Backend + Worker)
- Python 3.x with type hints
- FastAPI for REST endpoints with Pydantic models for validation
- SQLAlchemy async ORM with asyncpg driver
- Alembic for database migrations
- Snake_case for variables, functions, modules
- PascalCase for classes and SQLAlchemy models
- Environment variables for configuration (e.g. `DATABASE_URL`)
- Stateless backend — all state in PostgreSQL

## TypeScript / Vue (Frontend)
- Vue 3 Composition API with `<script setup lang="ts">`
- Single-file components (`.vue`)
- Pinia for state management
- Tailwind CSS for styling (utility-first)
- TypeScript strict mode enabled
- PascalCase for components, camelCase for variables/functions

## General
- No authentication/authorization in MVP
- Immutable versioning from `VERSION` file
- Docker Compose for local dev, Helm for Kubernetes
- All changes tested locally via `docker compose up` before committing
