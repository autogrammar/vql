# Ticket 003: Preserve rescued program-grid regression contract

- **ID**: ticket-003
- **Owner**: unresolved:human
- **Status**: DONE
- **Workflow state**: REVIEW
- **Session execution authorization**: user requested "kontynuuj" on 2026-08-20
- **Created**: 2026-08-20

## Goal and scope

Preserve the only unique behavior-level artifact from the rescued dirty VQL
copy: a focused regression test for maximal uniform rectangle merging. The
eleven rescued source refactors are superseded by newer canonical refactors and
must not overwrite them.

## Acceptance criteria

- [x] AC-01: Continued execution is authorized by the user's "kontynuuj".
- [x] AC-02: The rescued maximal-rectangle contract is present as a focused test.
- [x] AC-03: Focused and existing screenshot-grid tests pass (2/2).
- [x] AC-04: Repository governance validation passes with zero warnings.

## Participants

- Human participant: unresolved; no user-* file was created by this script.
- Agent participant: [ai-codex.md](ai-codex.md)
