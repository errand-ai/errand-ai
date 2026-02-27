# Stage 1: Build frontend (runs natively on build platform — output is platform-independent JS/CSS)
FROM --platform=$BUILDPLATFORM node:20-alpine AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Download Python wheels (runs natively, downloads wheels for target platform)
FROM --platform=$BUILDPLATFORM python:3.12 AS build
ARG TARGETPLATFORM
WORKDIR /app
COPY errand/requirements.txt .
RUN <<EOF
  set -e
  case "$TARGETPLATFORM" in
    linux/amd64) PLATFORM="manylinux2014_x86_64" ;;
    linux/arm64) PLATFORM="manylinux2014_aarch64" ;;
  esac
  pip download --no-cache-dir \
    --only-binary=:all: \
    --platform "$PLATFORM" \
    --python-version 312 \
    --implementation cp \
    --abi cp312 \
    -d /wheels \
    -r requirements.txt
EOF

# Stage 3: Final image (target platform — minimal QEMU usage: apt-get + pip install from local wheels)
FROM python:3.12-slim
ARG APP_VERSION="dev"
ENV APP_VERSION=$APP_VERSION
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY errand/requirements.txt .
COPY --from=build /wheels /tmp/wheels
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r requirements.txt && rm -rf /tmp/wheels
COPY errand/ .
COPY --from=frontend-build /frontend/dist ./static/
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
