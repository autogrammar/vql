# Changelog for Ticket 008

## Added
- Adopted wellmanifest/new-project 0.20.35 (`cfaa0bf0ea6b0e7349fed0bb62b5ce15792d687d`).
- Pinned Dockerfile and Dockerfile.e2e to immutable digest `python:3.12-slim@sha256:229a8f4c227ebfaeb32a76f2b4cbeec94589d96e57922d5f80b91d2222e964b0`.
- Added `[tool.wellmanifest]` section in `pyproject.toml` and configured `pytest_plugins = ["wellmanifest_governance"]`.
- Harmonized workstream paths and dependency manifests in `.governance/manifest.json`.
- Configured `.governance/ticket-activity.override.json` with `missingPolicy: git-ancestry`.
- Reconciled historical tickets 001, 004, 006 to DONE.
