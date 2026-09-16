# Ticket 007: Send VQL image completions through SubLLM vision

- **ID**: ticket-007
- **Owner**: unresolved:human
- **Status**: DONE
- **Created**: 2026-09-16

## Goal and scope

Route VQL image-completion requests through the central `subactor/subllm`
vision transport as part of the fleet-wide SubLLM vision rollout.

## Acceptance criteria

- [x] AC-01: Image completions submit through SubLLM vision.
- [x] AC-02: `mcp2vql` gate passes at the exact head.

## Session authorization

Continuation of the 2026-09-16 automation-completion session authorized by
the repository owner.
