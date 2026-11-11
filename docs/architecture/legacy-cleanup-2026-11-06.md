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
- Three combat re-export shims removed after migrating the remaining test imports to `services.combat`: `services/combat_encounter_service.py`, `services/combat_attack_service.py`, and `services/weapon_equipment_service.py`. The runtime already consumed the canonical package; service implementations and combat behavior are unchanged.
- Two further flat re-export shims, `services/character_creation_service.py` and `services/campaign_clock_service.py`, were removed after migrating their test consumers to `services.characters` and `services.campaign`; the package implementations and exports were already canonical.
- Eight further flat re-export shims were removed after confirming their only remaining consumers were compatibility-import tests: `services/durable_turn_challenge_state_service.py`, `services/durable_turn_clarification_submission_service.py`, `services/durable_turn_manual_roll_submission_service.py`, `services/durable_turn_narration_service.py`, `services/durable_turn_preparation_mapper.py`, `services/durable_turn_prepared_commit_service.py`, `services/durable_turn_result_mapper.py`, and `services/turn_resolution_codec.py`. Their canonical implementations and public exports remain in `services.turns`; behavior and persisted turn data are unchanged.
- Four final flat LLM/world re-export shims were removed after migrating three test modules to `services.llm_world` and confirming `services.world_state_port` had no consumers: `services/llm_world_context_renderer.py`, `services/llm_world_proposal_prompt_builder.py`, `services/llm_world_proposal_validator.py`, and `services/world_state_port.py`. Implementations and package exports remain unchanged.
- The LLM provider boundary is now a real package: `llm_provider.py`, `ollama_provider.py`, `fake_llm_provider.py`, and `llm_settings.py` moved into `services/providers/`. Production and test imports now use `services.providers`; the old flat modules were removed without changing provider behavior.
- `PersistentEffectService` and `EffectiveConditionService` moved into `services/campaign/`; all runtime and test imports use the canonical package. The old flat modules were removed after checking their in-repository consumers; effect persistence and condition projection behavior are unchanged.
- `DMService` moved into `services/turns/`; runtime and tests now use the canonical turn package. The old `services/dm_service.py` module was removed after migrating all in-repository consumers; narrative generation behavior is unchanged.

## Still legacy, but not dead

| Area | Why it remains | Deletion gate |
|---|---|---|
| Remaining flat service re-export modules | A smaller set of compatibility modules still exists; not all have been migrated | Repeat the consumer audit per module, migrate production and test imports, verify repository-wide references and CI, then remove each shim |
| `CampaignTurnService` | No longer constructed by the app/runtime composition or exposed through app proxies; retained only as an isolated compatibility implementation with direct unit tests | Confirm no external in-process consumers, then remove the implementation and its dedicated tests |
| `POST /integration/turn` and `LegacySillyTavernTurnService` | Deprecated route still dispatches to the legacy service | Observe zero usage for an agreed window and confirm supported extension clients have migrated |
| `WorldSnapshotRepository` and snapshot tables | Used by legacy SillyTavern transcript reconciliation and covered by tests | Retire the legacy route first; preserve existing user data and provide a deliberate migration before dropping tables |
| Remaining runtime proxies and legacy app exports | Other historical service proxies remain exposed for routers/tests | Migrate each consumer to explicit request/runtime dependencies, then remove the proxy and exports with regression coverage |
| Flat combat/provider modules | Combat and provider implementations have been moved into their capability packages; their former flat import paths are retired | Keep canonical import-boundary tests and avoid reintroducing flat compatibility paths |

## Cleanup rules

1. Search production code, tests, scripts, and documentation for imports/references before deleting a module.
2. Migrate callers before deleting compatibility shims; do not keep tests importing a shim merely to prove the shim works.
3. Keep regression tests for active behavior. Delete tests only when the behavior itself is intentionally retired.
4. Treat deprecated HTTP routes, persistence tables, and stored data as a coordinated compatibility/data migration, not ordinary dead-code cleanup.
5. Run Ruff, Python tests, and JavaScript tests in CI for every cleanup PR.
