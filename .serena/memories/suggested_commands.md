# Suggested Commands

## Local Development
```bash
# Start all services (postgres, migrations, backend, worker, frontend)
docker compose -f testing/docker-compose.yml up

# Rebuild images after Dockerfile changes
docker compose -f testing/docker-compose.yml up --build

# Stop and remove containers
docker compose -f testing/docker-compose.yml down

# View logs for a specific service
docker compose -f testing/docker-compose.yml logs -f backend
docker compose -f testing/docker-compose.yml logs -f worker
docker compose -f testing/docker-compose.yml logs -f frontend
```

## Backend Development
```bash
# Install Python dependencies
pip install -r backend/requirements.txt

# Run backend locally (outside Docker)
cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run worker locally
cd backend && python -m worker

# Run Alembic migrations
cd backend && alembic upgrade head

# Create a new migration
cd backend && alembic revision --autogenerate -m "description"
```

## Frontend Development
```bash
# Install dependencies
cd frontend && npm install

# Dev server with HMR
cd frontend && npm run dev

# Production build
cd frontend && npm run build
```

## Docker
```bash
# Build frontend image
docker build -t content-manager-frontend frontend/

# Build backend image
docker build -t content-manager-backend backend/
```

## OpenSpec Workflow
```bash
openspec list --json                      # List active changes
openspec status --change "<name>" --json  # Check change status
openspec new change "<name>"              # Start a new change
```

## System Utils (macOS / Darwin)
```bash
git status                               # Check git status
git diff                                 # View unstaged changes
git log --oneline -10                    # Recent commits
```
