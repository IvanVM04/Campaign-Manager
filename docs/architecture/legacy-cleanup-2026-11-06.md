# Legacy cleanup inventory

**Baseline:** `main` at `aa4239e22750e6e75ab915440c3107f02aaca75e` (2026-11-06)

This inventory separates confirmed dead code from compatibility code that still has consumers. Age or a legacy name alone is not a deletion criterion.

## Removed in this cleanup

- `services/identity_service.py`: its text-normalization and name-matching helpers have no source-code callers in the repository. No dynamic import or plugin registration references were found in the source search.
- `data/database.py`: tracked zero-byte artefact with no imports. The actual SQLite implementation remains `database.py`.

## Still legacy, but not dead

| Area | Why it remains | Deletion gate |
|---|---|---|
| Flat service re-export modules | Existing tests and some production modules still import them | Migrate every production and test import to the canonical package; verify repository-wide references and CI; then remove shims |
| `CampaignTurnService` | Still constructed by the app/runtime composition and used by compatibility tests | Remove its runtime wiring and compatibility factory after all consumers are migrated |
| `POST /integration/turn` and `LegacySillyTavernTurnService` | Deprecated route still dispatches to the legacy service | Observe zero usage for an agreed window and confirm supported extension clients have migrated |
| `WorldSnapshotRepository` and snapshot tables | Used by legacy SillyTavern transcript reconciliation and covered by tests | Retire the legacy route first; preserve existing user data and provide a deliberate migration before dropping tables |
| Runtime proxy and legacy app exports | Compatibility surface used by older routers/tests | Move consumers to explicit runtime/request dependencies and remove the exports with regression coverage |
| `services/campaign_runtime.py` | Compatibility import used by test setup | Migrate its remaining imports before deletion |
| Flat combat/provider modules | Their target package directories are documentation-only; source has not yet migrated | Map public contracts and dependencies before moving code; do not delete or relocate by naming convention |

## Cleanup rules

1. Search production code, tests, scripts, and documentation for imports/references before deleting a module.
2. Migrate callers before deleting compatibility shims; do not keep tests importing a shim merely to prove the shim works.
3. Keep regression tests for active behavior. Delete tests only when the behavior itself is intentionally retired.
4. Treat deprecated HTTP routes, persistence tables, and stored data as a coordinated compatibility/data migration, not ordinary dead-code cleanup.
5. Run Ruff, Python tests, and JavaScript tests in CI for every cleanup PR.
