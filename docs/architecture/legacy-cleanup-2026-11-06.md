# Legacy cleanup inventory — current disposition

This document began as an inventory on 2026-11-06. The implementation status below was revalidated during the 2026-11-12 cleanup.

## Retired

- RuntimeProxy and module-level runtime proxies.
- CampaignTurnService.
- Flat service re-export modules and old root-level provider/service aliases.
- Narrative-first `LLMWorldExtractor.extract()` and its callable facade.
- `LLMWorldPromptBuilder` and the `legacy_prompt_sections/` static prompt modules.
- Deprecated `POST /integration/turn` and `LegacySillyTavernTurnService`.
- `WorldSnapshotRepository`, `TurnRecord.snapshot` and the runtime `turns.snapshot` column.
- Tests that exclusively covered those retired behaviors.

## Preserved

- One durable native/SillyTavern lifecycle: resolve, challenge continuation and complete.
- Context/history and external transcript-state reads in the active SillyTavern adapter.
- Existing transcript versioning, external ID identity and challenge history.
- Historical non-null snapshot JSON, archived by migration 029 into `turn_snapshot_archive`.

## Data migration

Migration 029 creates the inert archive table, copies every non-null legacy snapshot payload with its turn and campaign IDs, and drops the former `turns.snapshot` column. The archive is not a second runtime source of truth and has no restore operation. Fresh databases and upgrades from earlier supported schema versions converge on schema version 29.

## Rules for future cleanup

1. Search production code, tests, scripts, docs and supported clients before removing a public or persisted contract.
2. Migrate callers before deleting compatibility shims.
3. Retain regression tests for active behavior; remove tests only when the behavior is intentionally retired.
4. Treat schemas and stored data as deliberate forward migrations.
5. Require Ruff, Python and JavaScript tests, Pyright scopes and CodeQL checks to pass before merging.
6. Do not reintroduce a parallel legacy turn/extraction pipeline.
