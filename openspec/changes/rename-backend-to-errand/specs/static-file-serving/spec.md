## MODIFIED Requirements

### Requirement: Combined Docker image
The application SHALL be built as a single Docker image using a multi-stage Dockerfile. The first stage SHALL use Node.js to build the frontend (`npm ci && npm run build`). The final stage SHALL use Python and copy the frontend build output into a `static/` directory alongside the application code. The build context SHALL be the repository root. The Dockerfile SHALL copy application source from `errand/` and requirements from `errand/requirements.txt`.

#### Scenario: Image contains frontend assets
- **WHEN** the Docker image is built
- **THEN** the final image contains `static/index.html` and `static/assets/` with the Vite build output

#### Scenario: Image does not contain Node.js
- **WHEN** the Docker image is built
- **THEN** the final image does not include Node.js, npm, or frontend source files

#### Scenario: Build context is repo root
- **WHEN** the Docker image is built
- **THEN** both `frontend/` and `errand/` directories are accessible in the build context
