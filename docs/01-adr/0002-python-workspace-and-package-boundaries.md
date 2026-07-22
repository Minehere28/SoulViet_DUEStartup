# ADR-0002: Python Workspace and Package Boundaries

- **Status:** Accepted
- **Date:** 2026-07-22
- **Decision owner:** SoulViet AI team
- **Applies from:** Phase 1 canonical Travel IR compiler slice

## Context

The repository cleanup is complete. The first executable slice needs a reproducible Python toolchain and an import structure that makes the compiler-first architecture enforceable without prematurely creating infrastructure adapters, web applications, or future packages.

The first slice is deliberately small: compile a fixture CSV into canonical Travel IR and emit a JSON validation report through a CLI. It must run without a database, model provider, web framework, vector store, or agent runtime.

## Decision

### Supported Python

Phase 1 supports **Python 3.11.x** only. Every project package will declare:

```toml
requires-python = ">=3.11,<3.12"
```

Python 3.11 is selected because it is the reviewed local runtime and provides the standard-library features required by this slice. Supporting another minor version requires explicit CI coverage and a new ADR or an amendment to this one.

### Project and dependency management

Use PEP 621 `pyproject.toml` configuration and a single **uv workspace**:

- the root `pyproject.toml` owns workspace membership and shared tool configuration;
- each executable package or application owns a small member `pyproject.toml` with its own distribution metadata and declared local dependencies;
- `uv.lock` is committed whenever dependencies are introduced or changed;
- the root development dependency group owns `pytest`, `mypy`, and `ruff`.

The canonical-IR compiler slice has **no third-party runtime dependency**. CSV parsing, JSON serialization, CLI parsing, hashing, UUIDs, date/time parsing, and data classes use the Python standard library. `pytest`, `mypy`, and `ruff` are development tooling only.

Do not add Pydantic, Click, Typer, FastAPI, database drivers, or any retrieval/model SDK for this slice. The standard library is sufficient and keeps the first contracts portable.

### Package layout and naming

Choose a workspace **package layout**, not a single repository-root `src/` layout:

```text
packages/contracts/src/soulviet_contracts/
packages/compiler/src/soulviet_compiler/
apps/cli/src/soulviet_cli/
```

The corresponding Python distributions are:

- `soulviet-contracts` → import package `soulviet_contracts`;
- `soulviet-compiler` → import package `soulviet_compiler`;
- `soulviet-cli` → import package `soulviet_cli`.

Packages are versioned, released, and deployed together as one modular monolith. The separate distributions are import and ownership boundaries, not independently deployed services or microservices.

### Dependency direction and ownership

The general repository direction remains:

```text
apps -> services -> packages
```

For a slice without an infrastructure adapter, an app may compose domain packages directly. Therefore the Phase 1 dependency graph is:

```text
soulviet-cli -> soulviet-compiler -> soulviet-contracts
```

No `services/` member is created until a vertical slice needs a real external integration.

Rules:

- `soulviet-contracts` is dependency-free and may import only the Python standard library.
- `soulviet-compiler` may import the standard library and `soulviet_contracts`; it may not import an app or service.
- `soulviet-cli` owns argument parsing, file-system invocation, exit codes, and JSON presentation; it may not contain parsing or domain-validation logic.
- A future `services/*` adapter may depend on packages but never on apps; it owns external clients and configuration translation, not domain rules.
- Domain packages must not import FastAPI, database drivers, Qdrant, Neo4j, model-provider SDKs, embedding libraries, agent frameworks, or service modules.
- `packages/ontology`, when introduced, must remain dependency-free. A future compiler may depend on it, but it may not depend on the compiler.

An architecture test based on the Python AST will reject prohibited imports. Dependency declarations must also make prohibited imports impossible in normal installation.

### Testing, type checking, linting, and formatting

- Use `pytest` for unit and integration tests.
- Use `mypy --strict` for all created source packages; do not introduce untyped public interfaces.
- Use Ruff for linting and formatting, targeting Python 3.11.
- Put shared tool configuration in the root `pyproject.toml`.
- Tests must import installed workspace packages, not rely on incidental repository-root imports.

The first implementation will add tests together with the contracts and compiler. This ADR adds no package, tool, or dependency today.

### CLI strategy

CLI applications are composition roots under `apps/`. The first command is a console-script entry point:

```text
soulviet-compile-fixture = soulviet_cli.main:main
```

The command accepts paths and presentation options, invokes the compiler package, writes the documented JSON envelope, and returns documented exit codes. It does not expose a web API and does not own canonical contract definitions.

## Consequences

### Positive

- A clean dependency graph exists before code is written.
- The first slice is reproducible without infrastructure or runtime secrets.
- Canonical contracts can be reused by later compiler, retrieval, planning, validation, and delivery slices.
- Tooling is standardised without selecting a web or AI framework.

### Costs

- A workspace has more metadata files than a one-folder prototype.
- Developers need `uv` available to resolve the locked environment.
- Boundary tests and strict typing require deliberate imports and explicit data modelling.

## Rejected alternatives

### Keep a root-level `src/` package

Rejected because it obscures the ownership boundaries required by `AGENTS.md` and makes it easier for delivery or infrastructure code to leak into domain code.

### One unstructured application package

Rejected because the compiler and its contracts must survive future delivery mechanisms without importing a CLI, API, or service adapter.

### Add a service layer now

Rejected because the fixture compiler has no external integration. An empty `services/` tree would be a placeholder, contrary to the rebuild rules.

### Add a framework for contracts or CLI parsing

Rejected because the standard library fully covers this slice and new runtime dependencies would add policy before a measurable need exists.

## Compliance and revisit triggers

The Phase 1 specification must define the exact workspace members, package files, development commands, and architecture test. Revisit this ADR if Python 3.12+ support, multiple independently released packages, a non-CLI delivery mechanism, or a dependency-management tool change becomes necessary.
