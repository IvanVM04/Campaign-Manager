# Migration catalogue

**Current schema version:** 34  
**Execution registry:** `MIGRATIONS` in `migrations.py`  
**Historical source:** the numbered `migration_NNN` functions remain in their existing chronological order in `migrations.py`.

The registry is the discoverability and execution index. It does not move, rewrite or reorder historical migration bodies, and it does not change the database schema by itself. New migrations are forward-only: add the next numbered function, add its metadata entry at the end of `MIGRATIONS`, increase `CURRENT_VERSION`, and add upgrade/preservation tests.

| Version | Function | Purpose |
|---:|---|---|
| 001 | `migration_001` | Create the initial campaign, entity, item, resource, session and event schema. |
| 002 | `migration_002` | Remove obsolete pre-campaign tables. |
| 003 | `migration_003` | Introduce persistent character mechanics state. |
| 004 | `migration_004` | Add the campaign active-character pointer. |
| 005 | `migration_005` | Seed the initial campaign record. |
| 006 | `migration_006` | Introduce campaign turn history. |
| 007 | `migration_007` | Add external turn identity. |
| 008 | `migration_008` | Add turn versioning and reconciliation metadata. |
| 009 | `migration_009` | Correct turn-versioning indexes and constraints. |
| 010 | `migration_010` | Allow retrying failed turn versions. |
| 011 | `migration_011` | Scope existing records and turn history to multiple campaigns; assign existing data to campaign 1. |
| 012 | `migration_012` | Enforce campaign-scoped names and prevent cross-campaign references. |
| 013 | `migration_013` | Validate campaign pointers against records in the same campaign. |
| 014 | `migration_014` | Clear campaign pointers when referenced records are deleted. |
| 015 | `migration_015` | Persist skill, expertise and saving-throw proficiencies. |
| 016 | `migration_016` | Persist campaign-scoped combat encounter snapshots. |
| 017 | `migration_017` | Add typed weapon metadata, proficiencies and equipment references. |
| 018 | `migration_018` | Persist campaign-scoped effects. |
| 019 | `migration_019` | Add the authoritative fictional campaign-time clock. |
| 020 | `migration_020` | Persist campaign-time deadlines for effects. |
| 021 | `migration_021` | Track monotonic revisions for campaign-owned state. |
| 022 | `migration_022` | Persist recoverable durable turn-resolution attempts. |
| 023 | `migration_023` | Record the campaign revision produced by a committed turn. |
| 024 | `migration_024` | Persist canonical NPC creature mechanics outside encounter snapshots. |
| 025 | `migration_025` | Add encounter-round and encounter-turn effect deadlines. |
| 026 | `migration_026` | Make equipment assignment campaign-scoped and slot-based. |
| 027 | `migration_027` | Add typed armor definitions. |
| 028 | `migration_028` | Persist light, medium, heavy armor and shield proficiencies. |
| 029 | `migration_029` | Archive historical turn snapshots before removing the runtime snapshot column. |
| 030 | `migration_030` | Persist class Hit Dice, used Hit Dice and the last completed long-rest campaign-time marker. |
| 031 | `migration_031` | Persist explicit entity aliases for deterministic reference resolution. |
| 032 | `migration_032` | Persist event epistemic status, provenance, character visibility, campaign time and supersession references. |
| 033 | `migration_033` | Persist versioned player-intent analysis plus its exact source text/fingerprint on durable turn resolutions; prevent edits after commit. |
| 034 | `migration_034` | Persist SillyTavern conversation identity on transcript turns and durable resolutions, with chat-scoped history indexes. |

Migration 031 adds `entities.aliases` as JSON text with an empty-list default; historical entities do not receive inferred aliases. Migration 032 adds typed event metadata with safe legacy defaults (`confirmed`, `gm_authored`, `public`), converts legacy secret events to `gm_only`, and protects source/superseded-event references from crossing campaign boundaries.

Migration 033 adds nullable `turn_resolutions.intent_json` so existing durable records remain readable. New prepared/challenge states store a versioned analysis envelope containing the full source text, a SHA-256 fingerprint and the strict analysis object. A trigger prevents changing intent evidence after a resolution is committed, narration-pending or completed.

Migration 034 adds nullable `conversation_id` columns to `turns` and `turn_resolutions`, preserving historical rows while binding new SillyTavern turns and continuations to one chat. It adds campaign/chat/session history and durable-resolution lookup indexes. The normal registry runner now declares schema version 34.

## Runner invariants

- Registry versions are contiguous and start at 1.
- Each registry entry's name matches its callable migration function.
- The runner advances `PRAGMA user_version` only after that migration returns successfully.
- A database already at the current version remains unchanged on a repeated run.
- Migration functions retain their existing transaction/savepoint behavior; the registry does not wrap them in a new transaction.
- Fresh-database initialization and upgrades from supported old versions remain covered by `tests/test_migrations.py`.

## Future migration checklist

1. Add `migration_034` (or the next sequential version) without editing earlier migration functions.
2. Add one `MigrationDefinition` at the end of `MIGRATIONS` and update `CURRENT_VERSION`.
3. Test upgrade from a relevant prior schema, old-data preservation, foreign keys and idempotency where appropriate.
4. Keep fresh-database initialization green and update this catalogue.
