# ADR-0001: Rebuild from `feat/engine-restructure-wip`

- **Status:** Accepted
- **Date:** 2026-07-22
- **Decision owner:** SoulViet AI team

## Context

Two existing branches are relevant:

- `LLM-recommend`
- `feat/engine-restructure-wip`

The second branch contains the history of `LLM-recommend` and additional restructuring work, documentation, source modules, and tests.

The project is being rebuilt around a compiler-first canonical-IR architecture with hybrid GraphRAG, deterministic planning, validation, and bounded agentic workflows.

The current implementation and documents must remain recoverable, but they must not constrain the new architecture.

## Decision

Create a new branch from:

```text
feat/engine-restructure-wip
```

Recommended new branch name:

```text
rebuild/career-os-v2
```

Do not continue implementation directly on either legacy branch.

The rebuild branch will remove obsolete runtime artifacts and legacy implementation files from the active tree while preserving their full history in Git.

## Why this branch

`feat/engine-restructure-wip` is the later branch and already contains the commits from `LLM-recommend`.

Starting from it provides:

- complete prior history;
- access to the most recent datasets and experiments;
- existing tests and documentation for review;
- the ability to recover selected business rules without merging branches later.

Starting from `LLM-recommend` would require reviewing or reintroducing later changes manually.

## Cleanup policy

On the new rebuild branch, review and normally remove or replace:

- `graph.pt`;
- `__pycache__/`;
- root experimental `app.py`;
- root experimental `index.html`;
- obsolete `src/`;
- obsolete architecture documents;
- dependency files tied only to the old runtime.

Review before retaining:

- raw datasets;
- normalization logic;
- fixtures;
- business-rule tests;
- parsing utilities with demonstrated correctness.

Do not copy old code into an in-tree `legacy/` folder. Git branches and history are the archive.

## Consequences

### Positive

- fastest path to a clean rebuild without losing work;
- no future merge needed to recover the newer branch;
- Codex can inspect history when asked;
- active source tree can remain unambiguous.

### Negative

- the first rebuild commit will contain many deletions;
- useful code must be selected deliberately rather than inherited implicitly;
- old documentation must be clearly removed or superseded to prevent AI confusion.

## Revisit triggers

Revisit this decision only if:

- the branch contains secrets or corrupted history;
- repository size makes history impractical;
- the AI Engine is moved into a new dedicated repository.
