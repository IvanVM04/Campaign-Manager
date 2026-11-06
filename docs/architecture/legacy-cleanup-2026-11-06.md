# Legacy cleanup inventory

**Baseline:** `main` at `20e7d49939c87249e7ad905abd11c135a892f207` (2026-11-06)

This inventory separates confirmed dead code from compatibility code that still has consumers. Age or a legacy name alone is not a deletion criterion.

## Removed in this cleanup

- `services/identity_service.py`: its text-normalization and name-matching helpers have no source-code callers in the repository. No dynamic import or plugin registration references were found in the source search.
- `data/database.py`: tracked zero-byte artefact with no imports. The actual SQLite implementation remains `database.py`.
- `services/campaign_runtime.py`: its test consumers now import `CampaignRuntimeFactory` from `bootstrap.campaign_runtime`.
- Flat compatibility shims `services/campaign_state_service.py`, `services/character_applier.py`, `services/character_service.py`, `services/context_builder.py`, `services/llm_world_extractor.py`, `services/world_service.py`, and `services/turn_execution_lock.py`: all test consumers were migrated to the canonical `services.campaign`, `services.characters`, `services.context`, `services.llm_world`, `services.world`, and `services.turns` packages before deletion.
- Additional confirmed re-export shims `services/durable_native_turn_service.py`, `services/turn_resolution_service.py`, `services/world_applier.py`, `services/llm_world_prompt_builder.py`, and `services/llm_world_response_parser.py`: consumers now import from `services.turns`, `services.world`, and `services.llm_world`; compatibility-only tests were removed while canonical package export coverage remains.
- Seven more flat re-export shims removed after migrating production and test imports: `services/context_ranker.py`, `services/context_expander.py`, `services/context_renderer.py`, `services/world_serializer.py`, `services/world_item_applier.py`, `services/world_entity_applier.py`, and `services/llm_extraction_errors.py`. Their implementations remain in `services/context/`, `services/world/`, and `services/llm_world/` respectively.

## Still legacy, but not dead

| Area | Why it remains | Deletion gate |
|---|---|---|
| Remaining flat service re-export modules | A smaller set of compatibility modules still exists; not all have been migrated | Repeat the consumer audit per module, migrate production and test imports, verify repository-wide references and CI, then remove each shim |
| `CampaignTurnService` | No longer constructed by the app/runtime composition or exposed through app proxies; retained only as an isolated compatibility implementation with direct unit tests | Confirm no external in-process consumers, then remove the implementation and its dedicated tests |
| `POST /integration/turn` and `LegacySillyTavernTurnService` | Deprecated route still dispatches to the legacy service | Observe zero usage for an agreed window and confirm supported extension clients have migrated |
| `WorldSnapshotRepository` and snapshot tables | Used by legacy SillyTavern transcript reconciliation and covered by tests | Retire the legacy route first; preserve existing user data and provide a deliberate migration before dropping tables |
| Remaining runtime proxies and legacy app exports | Other historical service proxies remain exposed for routers/tests | Migrate each consumer to explicit request/runtime dependencies, then remove the proxy and exports with regression coverage |
| Flat combat/provider modules | Their target package directories are documentation-only; source has not yet migrated | Map public contracts and dependencies before moving code; do not delete or relocate by naming convention |

## Cleanup rules

1. Search production code, tests, scripts, and documentation for imports/references before deleting a module.
2. Migrate callers before deleting compatibility shims; do not keep tests importing a shim merely to prove the shim works.
3. Keep regression tests for active behavior. Delete tests only when the behavior itself is intentionally retired.
4. Treat deprecated HTTP routes, persistence tables, and stored data as a coordinated compatibility/data migration, not ordinary dead-code cleanup.
5. Run Ruff, Python tests, and JavaScript tests in CI for every cleanup PR.
