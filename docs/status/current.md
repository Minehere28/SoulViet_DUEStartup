# Current Status

## Phase

**Phase 0 — Repository and architecture foundation**

## Active objective

Review the active repository-rebuild specification, resolve its security and data-provenance gates, and then perform the minimum structural cleanup on the rebuild branch.

## Source branch

Create the rebuild from:

```text
feat/engine-restructure-wip
```

New branch:

```text
rebuild/career-os-v2
```

The old branches remain unchanged.

## Current architecture status

The legacy system is not the target architecture.

Known legacy characteristics include:

- root-level experimental application files;
- runtime dependency on `graph.pt`;
- prototype service/module layouts;
- deterministic-engine documentation that was written before the GraphRAG + agentic direction was finalized.

These are reference materials only.

## Active specification

The active specification is:

```text
docs/04-spec/0001-repository-rebuild.md
```

It inventories the current tree and defines the exact cleanup, retained assets, minimum tracked tree, acceptance criteria, and ADR blockers. No cleanup or engine implementation has been executed yet.

## Work allowed in this phase

Allowed:

- review branch contents;
- create the rebuild branch;
- replace root `README.md`;
- add `AGENTS.md`;
- add vision, ADR, and status documents;
- inventory files as retain, rewrite, archive-by-history, or delete;
- propose the first vertical slice.

Not allowed yet:

- implement GraphRAG;
- implement agents;
- create all target packages;
- choose final retrieval weights;
- migrate to Neo4j or a vector store;
- rewrite the entire engine in one task;
- preserve old modules without review.

## Proposed first commits

### Commit 1 — Foundation documents

- `README.md`
- `AGENTS.md`
- `docs/00-vision/00-project-vision.md`
- `docs/01-adr/0001-rebuild-from-engine-restructure.md`
- `docs/status/current.md`

### Commit 2 — Rebuild specification

Created in the working tree:

```text
docs/04-spec/0001-repository-rebuild.md
```

The specification must inventory the current tree and define exact file operations.

### Commit 3 — Structural cleanup

Delete obsolete generated and prototype artifacts. Keep only reviewed data and minimal project scaffolding.

No engine behavior should be added in this commit.

## Latest task record

- Created `docs/04-spec/0001-repository-rebuild.md`.
- Inventoried all 28 current `src/` Python files and all 23 pending legacy-document deletions.
- Recorded the replacement CSV schema, checksum, retention gate, and its incompatibility with the prototype mapper.
- Recorded a credential-like value in the deleted legacy CSV without reproducing it; credential and Git-history remediation require a focused decision.
- Verification performed: specification section/classification checks, explicit path-coverage checks, UTF-8 replacement-character check, and repository-status review.
- Runtime tests were not run because this task changes documentation only and adds no executable engine.
- Known limitation: the checkout remains `feat/engine-restructure-wip`; no branch ref, cleanup file, source file, test, or runtime artifact was changed by this task.
- Next recommended commit: accept the repository secret/Git-history remediation ADR before structural cleanup.

## Acceptance criteria for Phase 0

- [ ] `rebuild/career-os-v2` exists.
- [ ] Existing branches are unchanged.
- [ ] README explains the target system and current phase.
- [ ] AGENTS.md defines reading order and coding rules.
- [ ] ADR-0001 records the branch and rebuild strategy.
- [ ] Legacy documents no longer appear authoritative.
- [ ] The active tree contains no tracked `__pycache__`.
- [ ] `graph.pt` is not part of the new runtime design.
- [ ] The next implementation scope is a written vertical slice, not a global rewrite prompt.

## Known decisions still required

- Repository secret rotation and Git-history remediation.
- Travel-data provenance, licensing, snapshot relationship, and storage policy.
- Python workspace and packaging strategy.
- Canonical IR schema.
- Ontology node and edge taxonomy.
- Source-of-truth adapter contract.
- Initial structured-retrieval baseline.
- Evaluation dataset and metrics.
- Final infrastructure choices for graph and vector indexes.
- Workflow framework and agent-provider choices.

These decisions must be made through focused ADRs, not embedded into a single large system prompt.
