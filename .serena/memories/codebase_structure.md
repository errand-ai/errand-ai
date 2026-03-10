# Codebase Structure

```
content-manager/
├── VERSION                    # Semver version (e.g. 0.1.0)
├── CLAUDE.md                  # AI assistant instructions
├── README.md                  # Project readme
├── testing/docker-compose.yml  # Local dev environment
├── backend/                   # Python backend + worker
│   ├── __init__.py
│   ├── main.py                # FastAPI application
│   ├── models.py              # SQLAlchemy models
│   ├── database.py            # DB engine and session factory
│   ├── worker.py              # Worker polling loop
│   ├── requirements.txt       # Python dependencies
│   ├── alembic.ini            # Alembic configuration (to be created)
│   ├── alembic/               # Migration scripts (to be created)
│   └── Dockerfile             # Backend Docker image (to be created)
├── frontend/                  # Vue 3 frontend
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── index.html
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── assets/main.css
│   │   ├── components/        # Vue components
│   │   ├── stores/            # Pinia stores
│   │   └── composables/       # Vue composables
│   ├── nginx.conf             # Nginx config (to be created)
│   └── Dockerfile             # Frontend Docker image (to be created)
├── helm/content-manager/      # Helm chart (to be created)
├── .github/workflows/         # CI/CD pipelines (to be created)
└── openspec/                  # OpenSpec change management
    ├── config.yaml
    ├── specs/
    └── changes/
```
