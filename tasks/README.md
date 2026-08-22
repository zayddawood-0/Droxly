# Doxly — Implementation Tasks

> This directory holds individual implementation task files once implementation begins. **No implementation tasks are defined yet** — this file defines *how* tasks will be structured so that Claude Code and human contributors create them consistently, per phase, from `specs/roadmap.md`.

## Purpose

A task is the unit of work that sits between a roadmap phase (`specs/roadmap.md`) and actual source code. Each task:

- Implements one coherent, reviewable slice of a phase (not an entire phase in one task, and not a single trivial function either — aim for "one PR" granularity).
- Is traceable back to specific requirement IDs in `specs/requirements.md` and the specs that define its behavior.
- Is not created until its phase is actively being worked, so it reflects the current, not stale, state of the specs.

## Task file naming

`tasks/{phase-number}-{kebab-case-slug}.md`, e.g. `tasks/02-user-registration.md`, `tasks/05-pdf-text-extraction.md`.

## Task template

Every task file MUST follow this structure:

```markdown
# Task {ID}: {Title}

## Task ID
{PHASE}-{SEQUENCE}, e.g. P02-001

## Feature
{One-line feature area, e.g. "Authentication — Email/Password Registration"}

## Objective
{1-3 sentences: what this task delivers and why it matters, in plain language}

## Specification References
- {spec file}#{section} — {what it defines that's relevant here}
{List every spec file this task must be consistent with. At minimum: the owning domain spec (e.g. requirements.md, api.md, database.md) — never implement against tribal knowledge not present in specs/.}

## Requirements
- {FR-/NFR- ID}: {short restatement of the acceptance criteria being satisfied}
{Every requirement ID this task fulfills, in whole or in part. If only partially fulfilling a requirement, say which acceptance criteria remain for a later task.}

## Dependencies
- {Task ID or Phase} — {why it must come first}
{Other tasks, migrations, or infrastructure that must exist before this one can be implemented.}

## Files Affected
- {path} — {new | modified} — {one-line purpose}
{Every file expected to be touched, known up front where possible. Update this list if implementation reveals more files are needed — do not silently expand scope beyond what the Objective describes.}

## Implementation Notes
{Architectural or approach guidance specific to this task — layering rules from skills/backend.md or skills/frontend.md that apply, edge cases called out in the relevant spec, things explicitly NOT in scope for this task (deferred to a later task) so scope doesn't creep.}

## Tests
- {test type, per specs/testing.md} — {what it must verify}
{Map to specs/testing.md's traceability table for this requirement. Every P0 requirement in this task needs at least one listed test.}

## Acceptance Criteria
{Copied/adapted directly from specs/requirements.md's Given/When/Then criteria for the requirement IDs above — the task is not done until these pass, verified, not assumed.}

## Definition of Done
- [ ] Code implements the Objective and satisfies all Acceptance Criteria
- [ ] Tests listed above are written and passing
- [ ] No requirement silently changed or reinterpreted — if a spec gap or contradiction was found during implementation, it was resolved by updating the spec first (see CLAUDE.md SDD rules), not by improvising
- [ ] Relevant spec file(s) updated if this task revealed a necessary spec change
- [ ] Linked in the PR description with the requirement IDs and phase
```

## Workflow

1. A phase in `specs/roadmap.md` becomes active.
2. Tasks are created for that phase's objectives, sized to "one reviewable PR" each, using the template above.
3. Each task is implemented against the CURRENT state of `specs/` — if the spec is unclear or contradictory, the spec is fixed first (per `CLAUDE.md`'s SDD rules), then the task proceeds.
4. On completion, the task's Definition of Done is checked off in the PR, and `specs/roadmap.md`'s phase status can be updated to reflect progress (not done automatically — update it deliberately when a phase's Definition of Done, from roadmap.md, is actually met).

## What does NOT belong in a task file

- Full requirement text (link to `specs/requirements.md` by ID instead of copy-pasting the whole requirement).
- Speculative future work not in the current phase.
- Decisions that belong in `specs/decisions.md` (an ADR) rather than buried in one task's implementation notes — if a task's implementation requires a real architectural choice not already covered by an ADR, add the ADR first.
