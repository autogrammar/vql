# Ticket 002: Add CLI entry point and fix testql scenario

- **ID**: ticket-002
- **Owner**: unresolved:human
- **Status**: DONE
- **Workflow state**: REVIEW
- **Session execution authorization**: user requested "kontynuuj" — autonomous CLI and scenario fixes within allowedPaths
- **Created**: 2026-08-17

## Goal and scope

Provide a `python -m vql` CLI entry point and align the generated TestQL
scenario with its user-visible help output.

## Acceptance criteria

- [x] AC-01: `python -m vql --help` and `--version` exit successfully.
- [x] AC-02: The generated CLI TestQL scenario passes all seven assertions.
- [x] AC-03: Repository governance validation passes.

## Participants

- Human participant: unresolved; no user-* file was created by this script.
- Agent participant: [ai-devin.md](ai-devin.md)
- Verification participant: [ai-codex.md](ai-codex.md)
