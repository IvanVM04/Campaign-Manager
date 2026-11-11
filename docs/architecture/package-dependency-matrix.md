# Capability-package dependency matrix

**Status:** initial enforceable baseline, introduced with PR #150.

This matrix describes dependency direction for the eight capability packages under `services/`. It is deliberately conservative: it records boundaries that current code can enforce without a broad relocation or behavior change. A dependency not explicitly discussed below is not automatically endorsed; update this document and its architecture test in the same PR when introducing a new cross-package edge.

## Shared layers

Capability packages may use the shared layers needed by their responsibilities:

- `models` — domain state and typed read/write models.
- `operations` — typed commands and proposals.
- `repositories` — persistence ports/adapters currently used by application services.
- `rules_engine` — deterministic ruleset mechanics.

The rules engine remains independent of API, database, repositories, LLM providers and service orchestration. API routers are transport adapters and must not be imported by service packages. Runtime construction belongs to `bootstrap`, not capability packages.

## Capability-package matrix

| Package | Allowed cross-package service dependencies | Forbidden dependencies enforced by tests |
|---|---|---|
| `campaign` | `services.world` state port; root effect/condition service | API, bootstrap, characters, combat, context, llm_world, providers, turns |
| `characters` | None | API, bootstrap and all other capability packages |
| `combat` | Character mechanics remain accessed through shared models/repositories/rules | API, bootstrap, campaign, context, llm_world, providers, turns, world |
| `context` | `services.world` serialization/projection | API, bootstrap, campaign, characters, combat, llm_world, providers, turns |
| `llm_world` | None; provider invocation is injected at its application boundary | API, bootstrap, database, repositories, campaign, characters, combat, context, providers, turns, world |
| `providers` | None; this is an adapter/port boundary | API, bootstrap, database, models, operations, repositories, rules_engine and service packages |
| `turns` | World application, LLM-world proposal boundary and mechanics orchestration | API and bootstrap |
| `world` | `services.characters` for typed character application | API, bootstrap, campaign, combat, context, llm_world, providers, turns |

The matrix is a set of enforced prohibitions, not a claim that every allowed edge is currently used. In particular, a package's permission to import a shared layer does not authorize bypassing its public contracts or transaction ownership.

## Composition and cross-cutting services

- `bootstrap/campaign_runtime.py` is the composition root and may wire capability packages together.
- `api/routers/` obtains the request-scoped runtime and translates HTTP input/output; it does not compose services.
- Root-level application services such as `DMService`, `MechanicsAdjudicator`, `OperationParser`, effect services and SillyTavern adapters remain outside the eight-package matrix until their ownership is decided.
- `MemorySearchService` belongs to `services/context`; it performs deterministic retrieval/export over a supplied `WorldState` and does not own persistence or campaign state.
- Legacy compatibility code is not a precedent for new dependencies. Do not expand its dependency surface.

## Updating the matrix

When a change needs a new dependency:

1. Confirm that the dependency reflects a stable responsibility rather than a convenient import.
2. Prefer a small protocol/value contract or move orchestration to the composition/application boundary when that reduces coupling.
3. Add the edge to this document with its direction and reason.
4. Update `PACKAGE_FORBIDDEN_IMPORTS` in `tests/test_architecture_boundaries.py` so the new edge is an explicit exception.
5. Run the architecture tests, Ruff, Python tests and JavaScript tests.

Do not introduce a generic dependency-injection framework or split the modular monolith merely to satisfy this matrix. The purpose is to make coupling visible and intentional while preserving the current working architecture.
