# Content Manager - Project Overview

## Purpose
A Kanban-style task processing application with a Vue 3 frontend, Python FastAPI backend, and a database-backed worker queue. Tasks are created via a web UI, stored in PostgreSQL, and processed by worker pods that auto-scale via KEDA.

## Status
Early development (MVP scaffold phase). The project uses OpenSpec for structured change management.

## Architecture
- **Frontend**: Vue 3 + Vite + Tailwind CSS + Pinia (SPA served by nginx)
- **Backend**: Python FastAPI + SQLAlchemy + Alembic (REST API, stateless)
- **Worker**: Python (same codebase as backend, separate entrypoint) — polls for tasks using `SELECT ... FOR UPDATE SKIP LOCKED`
- **Database**: PostgreSQL (externally provisioned, app manages schema via Alembic)
- **Deployment**: Helm chart on Kubernetes, KEDA for worker autoscaling, ArgoCD
- **CI/CD**: GitHub Actions, immutable versioning from `VERSION` file

## Key Design Decisions
- Database-as-queue (no external message broker for MVP)
- Single Docker image for backend + worker (different entrypoints)
- Alembic migrations run as Helm pre-upgrade hook Job
- Version sourced from single `VERSION` file at repo root
- Frontend built as static assets, served by nginx with `/api/*` proxy to backend
