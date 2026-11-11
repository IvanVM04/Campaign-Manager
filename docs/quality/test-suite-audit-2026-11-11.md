# Test-suite audit — 2026-11-11

**Repository:** `IvanVM04/Campaign-Manager`  
**Audited `main`:** `a0e2c70bedd8f3e45f40d4c4f39d4fee13f8d4eb` (PR #189)  
**Observed CI:** 1,313 Python test items collected; 1,306 passed and 7 live-LLM cases were deselected (Tests run #43103128009).  
**Method:** recursive test-tree inventory, file-size and test-name inspection, workflow marker configuration and selected contract-file review. This is a structural audit, not a claim that every assertion has been mutation-tested or individually executed outside CI.

## 1. Executive assessment

The suite is broad and is protecting important domain, persistence, API, LLM-boundary and durable-turn behavior. There is no evidence to justify broad test deletion.

The main maintenance problem is navigation and mixed responsibility in several very large files. Reorganization should preserve assertions and fixtures. Small files and one-test modules are not inherently redundant: they often protect a narrow public contract, migration invariant or regression boundary.

## 2. Current execution model

- Test discovery is configured under `tests/`.
- Deterministic CI runs `python -m pytest -m "not real_llm"`.
- Tests marked `real_llm` require a running local Ollama instance and a compatible model; they are deliberately deselected in normal CI.
- Coverage collection enables branch tracking and publishes `coverage.xml` as a workflow artifact.
- JavaScript tests run separately through `npm run test:js` and Node's built-in test runner.
- The shared `tests/conftest.py` creates a temporary SQLite database per test and resets the application runtime factory, which is an important isolation fixture.

## 3. Largest navigation hotspots

The former `test_silly_tavern_integration.py` was split by PR #186 into smaller API, lifecycle, service, schema and regeneration-failure modules. The current largest modules are:

| Module | Lines | Test functions | Primary contracts |
|---|---:|---:|---|
| `test_silly_tavern_lifecycle.py` | 2,441 | 16 | Versioned turn lifecycle, snapshots, retries/idempotency, rollback, restart and state persistence |
| `test_world_repository.py` | 1,817 | 24 | World persistence, atomic save, connection ownership, campaign isolation and snapshot restore |
| `test_world_service.py` | 1,679 | 38 | World loading/saving, typed operation application, rollback and in-memory/SQLite consistency |
| `test_turn_repository.py` | 1,420 | 39 | Turn persistence, campaign-scoped identities, transaction ownership, ordering and input validation |
| `test_turn_resolution_service.py` | 1,388 | 33 | Legacy narrative-first planner, structured proposals, deterministic mechanics and plan application |
| `test_durable_native_turn_service.py` | 1,206 | 25 | Durable commit, idempotency, narration recovery, clarification/manual rolls and failure recovery |
| `test_context_builder.py` | 1,181 | 47 | Retrieval, expansion, relevance, text budgets, structured context and recent history |
| `test_llm_world_extractor.py` | 1,152 | 35 | Legacy extraction, structured proposals, malformed output, parser validation and repair |
| `test_migrations.py` | 1,127 | 27 | Historical schema upgrades, data preservation, constraints and durable turn tables |

Other sizeable but reasonably cohesive modules include combat attack/opportunity workflows, world application, DM service and turn resolution repository contracts. Split them only when the new files reflect distinct externally observable responsibilities.

## 4. Keep, reorganize or investigate

### Keep as core regression coverage

- Durable turn lifecycle and repository tests: commit-before-narration, idempotency, revision fencing, lease/recovery behavior and short atomic write boundaries.
- Repository and migration tests: campaign isolation, connection/transaction ownership, rollback and historical data preservation.
- Rules-engine domain tests: deterministic mechanics should remain independent of LLM/provider behavior.
- World-operation and character-application tests: LLM proposals must not bypass typed validation or mutate unrelated state.
- Context tests: relevance ranking, secret-event filtering, stable ordering, and independent text/history budgets.
- Architecture tests: import boundaries and capability dependency direction are distinct constraints, not duplicates.
- Live-LLM tests: keep separately marked as integration/quality probes; do not make deterministic CI dependent on a local provider.

### Reorganize without changing behavior

1. PR #186 completed the first split of the former 4,000-line SillyTavern integration module into `test_silly_tavern_schemas.py`, `test_silly_tavern_api.py`, `test_silly_tavern_service.py`, `test_silly_tavern_lifecycle.py` and `test_silly_tavern_regeneration_failure.py`, with shared support in `silly_tavern_integration_support.py`. The next step is to split the remaining 2,441-line lifecycle module by versioning/retry, snapshot compatibility, rollback and persistence contracts.
2. Split `test_llm_world_extractor.py` into legacy narrative extraction and structured player-intent proposal/parser/repair behavior.
3. Split `test_context_builder.py` by retrieval/expansion, ranking/structured candidates and text/history rendering budgets.
4. Consider separating turn-planning behavior from plan-application behavior in `test_turn_resolution_service.py`, preserving end-to-end transaction tests in their owning integration modules.
5. Review `test_world_repository.py`, `test_world_service.py` and `test_turn_repository.py` for cohesive responsibility-based splits; do not create a separate test file per tiny test.
6. Keep durable recovery/fencing tests grouped by state transition. PRs #187 and #189 already added prepared-context fencing, runtime-restart recovery and idempotency-conflict coverage.

### Tiny tests and apparent duplicates

- `test_turn_resolution_service_compatibility.py` contains one test for canonical `services.turns` exports. Its filename suggests a retired compatibility behavior; rehome/rename the test under package API contract tests, but preserve its assertion.
- Small tests for operation result semantics, campaign-state defaults, effect projection, migration 019, serializers and character operation value objects each protect distinct contracts based on the current source. Do not remove them based on file size.
- `test_architecture_boundaries.py` checks dependency direction. `test_canonical_service_import_boundaries.py` checks that retired import paths remain absent and consumers use canonical modules. Their purpose differs; keep both unless a future consolidated test preserves all assertions and failure diagnostics.
- The historical compatibility tests for `CampaignTurnService` have already been removed together with the retired implementation in PR #156. Do not recreate them.

## 5. Coverage interpretation

The latest observed report from Tests run #43103128009 shows 85.8% line coverage and 72.6% branch coverage. This number alone does not indicate test quality. Package-level and branch-level review should prioritize:

- transaction rollback after partial failure;
- concurrent duplicate delivery and idempotency;
- stale campaign revision and expired lease recovery;
- retry after narration/provider failure without reapplying consequences;
- invalid JSON, malformed schema, unsupported operations and failed repair;
- secret-event and campaign/character knowledge boundaries;
- validation of all public API error paths;
- migration data preservation and foreign-key/campaign scope constraints.

A threshold should be introduced only after establishing a reproducible per-package baseline and protecting newly added behavior without forcing an unrelated global test campaign.

## 6. Deletion policy

No test deletion is approved by this audit alone.

A test may be deleted only if:
1. the behavior it protects is intentionally retired, or it is proven semantically duplicated;
2. all production, test, script and supported external consumers are checked;
3. the surviving test suite still protects the same externally observable contract;
4. deletion is included with the implementation/contract change in the same PR;
5. the PR documents which guarantee was removed and why.

Never delete tests to increase a coverage percentage or simply reduce file count.

## 7. Recommended sequence

1. Continue with the remaining SillyTavern lifecycle test split, preserving all assertions and fixtures.
2. Split legacy narrative extraction tests from active structured proposal/parser/repair tests.
3. Reorganize context tests around retrieval/expansion, ranking and rendering budgets.
4. Consider responsibility-based splits for turn resolution, world persistence/application and turn repository tests.
5. Use package/branch coverage to identify missing critical-path guarantees; keep percentage thresholds report-only until a no-regression policy is justified.
6. Reassess tiny tests only after their protected contracts are clearly mapped; move/rename rather than delete when still valid.
