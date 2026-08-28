# Ticket 004: Use canonical attribution for VQL LLM calls

- **ID**: ticket-004
- **Owner**: unresolved:human
- **Status**: IN_PROGRESS
- **Workflow state**: EDIT
- **Session execution authorization**: user requested “kontynuuj” — standardize VQL OpenRouter attribution.
- **Created**: 2026-08-28

## Goal and scope

Replace the legacy OpenRouter title header in the vision client while retaining
the dedicated vision model until SubLLM exposes a vision-capable route.

## Acceptance criteria

- [x] AC-01: `X-OpenRouter-Title` is emitted from `OPENROUTER_APP_NAME`.
- [x] AC-02: Existing vision request semantics remain unchanged.

## Participants

- Human participant: unresolved; no user-* file was created by this script.
- Agent participant: [ai-codex.md](ai-codex.md)
