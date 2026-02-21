## Why

Running the content-manager locally currently requires Docker, docker-compose knowledge, and terminal commands. A native macOS menu bar application would provide a one-click experience: start the entire stack, see service status, open the UI in a browser, and manage configuration — all from the menu bar. Using Apple's Containerization framework (native to macOS 26+, Apple silicon), the app runs OCI containers without requiring Docker Desktop, providing a lightweight, native experience.

This also enables distribution of content-manager as a standalone macOS application that non-technical users can install and run.

## What Changes

- **New macOS application**: SwiftUI menu bar app using `MenuBarExtra` for the UI
- **Apple Container orchestration**: Uses the Containerization Swift framework to pull, create, start, stop, and monitor OCI containers
- **Service management**: Manages PostgreSQL, Valkey, backend (with frontend), and worker containers; optionally manages LiteLLM
- **AppleContainerRuntime**: The worker communicates with the host Swift app to spawn task-runner containers (via a bridge API), as the worker runs inside a container and cannot directly invoke Apple Container
- **Persistent storage**: PostgreSQL and Valkey data stored in `~/Library/Application Support/ContentManager/` via volume mounts
- **App distribution**: Signed with Developer ID, notarized by Apple, distributed as a DMG outside the App Store

## Capabilities

### New Capabilities
- `macos-menu-bar-app`: SwiftUI application with service status, controls, and browser launch
- `apple-container-orchestration`: Container lifecycle management using Containerization.framework
- `litellm-optional-service`: Optional LiteLLM deployment for multi-provider LLM management
- `container-bridge-api`: HTTP API exposed by the Swift app for the worker to request task-runner container creation
- `app-distribution`: Code signing, notarization, DMG packaging for macOS distribution

### Modified Capabilities
- `container-runtime`: Add `AppleContainerRuntime` implementation (third runtime alongside Docker and K8s)

## Impact

- **New repository**: Separate Swift/Xcode project (not inside the content-manager repo)
- **Worker**: New `AppleContainerRuntime` in `backend/container_runtime.py` — communicates with the Swift app's bridge API to spawn task-runner containers
- **Images**: The app pulls pre-built content-manager images from GHCR (same images CI builds today)
- **Apple Developer Program**: Required for code signing and notarization ($99/year)
- **System requirements**: macOS 26+, Apple silicon Mac
