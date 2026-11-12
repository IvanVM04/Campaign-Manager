# Architecture and modularity audit — 2026-11-12

**Repository:** IvanVM04/Campaign-Manager  
**Verified baseline:** main at eb57316d9b060bb3a09b0b6b08c7282e07fce192 (PR #195, 2026-11-12).  
**Method:** recursive source-tree inventory, review of the current architecture/legacy/prompt/test/CI audits, package READMEs, dependency matrix, runtime composition, LLM extract/propose boundaries, combat services and representative persistence/rules modules.  
**Limitations:** no local test run, database migration replay, live Ollama call or manual SillyTavern session was executed during this audit. GitHub Actions results were inspected directly.

## Executive assessment

The repository has reached a useful modular-monolith baseline. All eight capability packages contain implementation code, the old flat service re-export layer has been removed, service-to-adapter direction is enforced, the runtime composition root is explicit, and the durable turn path has idempotency/recovery coverage.

Do not rewrite the application or split it into services. The remaining work is mainly about making existing boundaries authoritative, reducing oversized application coordinators, moving deterministic mechanics out of service code and keeping the deprecated integration path safely isolated.

The biggest current architectural risks are not the already-retired shims. They are:
- the large DurableNativeTurnService coordinator;
- the large CombatAttackService use case, which still contains attack-profile and NPC metadata translation;
- transaction/aggregate consistency across combat encounter and canonical character/creature HP;
- the mixed responsibilities in WorldService;
- a long-lived legacy narrative-first extraction path that is no longer the active durable proposal prompt.

## Verified repository state

The global navigation is split into complementary references: [architecture map](architecture-map-2026-11-12.md) for capability packages and end-to-end flows, [shared-layer module catalogue](module-catalog-2026-11-12.md) for transport, models, operations, persistence, rules, scripts and tests, and [change-impact map](change-impact-map-2026-11-12.md) for cross-layer consumers and regression requirements. All are linked from the documentation hub and coding-agent instructions.

### Capability boundaries

The eight service packages and their ownership are documented in the architecture map. The former root-level services compatibility shims and RuntimeProxy surface are already retired. The external SillyTavern Python adapter now lives under integrations/adapters/silly_tavern. Bootstrap owns construction; API routers obtain request-scoped runtime services.

The root services directory now consists of capability packages rather than an additional flat service façade. Do not recreate old import paths.

### Durable turn workflow

The active durable native path is DurableNativeTurnService -> TurnResolutionService -> ContextBuilder/ProposalContextSelector -> LLMWorldExtractor.propose() -> WorldService. It commits typed consequences durably before narration. Provider calls and narration must remain outside the atomic write transaction.

The 778-line DurableNativeTurnService is a coordinator across preparation, execution, clarification, manual rolls, external completion and recovery. It has extracted collaborators already; the next work should preserve the public façade while moving cohesive lifecycle workflows behind it, not create a second orchestration layer.

### LLM and prompt assessment

Keep the two pipelines distinct:

1. Active durable proposals: player intent is converted into typed, relevant WorldContextProjection data. Context selection, full prompt, response and one compact repair request have independent budgets. Operation metadata is centralized. Domain authorization and mutation remain downstream.
2. Legacy narrative-first extraction: extract() and the stable LLMWorldPromptBuilder facade are retained for the legacy planner branch and deprecated SillyTavern mutation route. The old prompt's static text is decomposed into eight ordered source modules and protected by a byte-for-byte rendered-prompt regression fixture.

PR #194 changed source organization, not prompt length or model output quality. The 46,851-character legacy prompt is not the active proposal prompt. It should not be shortened or rewritten without representative live-provider probes and consumer retirement evidence.

### SillyTavern compatibility

PR #195 separated active context/transcript reads from legacy mutation processing. The read adapter is independent of snapshot repositories and mutation workflows; the legacy processor is separately injected at bootstrap.

The deprecated POST /integration/turn route remains operational, and zero external usage has not been proven. WorldSnapshotRepository serializes state into JSON in the nullable turns.snapshot column; there are no dedicated snapshot tables. Preserve this route/data until the explicit observation-window, supported-client and retention gates in the legacy retirement audit are met.

### Rules and combat

The combat application package currently contains an oversized attack use case. It coordinates input guards, opportunity attacks, character/NPC state loading, NPC attack metadata parsing, equipment-derived profiles, conditions, damage, death-state transitions and atomic persistence.

The deterministic HP/death-track transition has been moved into rules_engine/dnd5e_2014/combat/hit_points.py in the companion refactor. It receives primitive state and returns a value object; it does not import models, repositories or services. This makes the engine own the rule transition while the service retains canonical-state synchronization and transaction ownership.

The next combat extraction should isolate player/NPC attack-profile resolution, then review transaction ownership for encounter, character/creature HP and effect updates. Do not move repository access into rules_engine.

### Other structural hotspots

| Area | Verified shape | Finding |
|---|---|---|
| DurableNativeTurnService | 778 lines | Next high-value application-coordinator decomposition. |
| CombatAttackService | 532 lines before the HP transition extraction | Profile and NPC metadata resolution remain mixed into the use case. |
| CombatEncounterService | 599 lines | Encounter lifecycle, movement, reaction and death-save use cases share one service; split only by stable transaction boundaries. |
| WorldService | 660 lines | State façade, dispatch and transaction coordination; preserve caller-owned connection semantics. |
| migrations.py | 2,298 lines / 28 ordered migration functions | Do not split history casually. Introduce an index first and require full replay/data-preservation tests. |
| models/schemas.py | 514 lines | Broad schema module; split by bounded context with stable import contracts. |
| bootstrap/campaign_runtime.py | 11 KB | Composition root, not a business-service dumping ground. Keep wiring centralized. |

## Cleanup disposition

### Confirmed retired

- RuntimeProxy and module-level runtime proxies.
- CampaignTurnService.
- Flat compatibility shims under services/.
- Old root SillyTavern integration module; adapter now belongs to integrations/adapters/silly_tavern.
- Old mixed LLM extractor tests and the former monolithic SillyTavern lifecycle test names were reorganized in PR #193 without deleting test functions.

Do not repeat these cleanup items.

### Retain with explicit retirement gates

- POST /integration/turn and LegacySillyTavernTurnService.
- WorldSnapshotRepository and existing snapshot JSON payloads.
- Nullable turns.snapshot schema column.
- Legacy extract() API and LLMWorldPromptBuilder facade while narrative-first compatibility consumers remain.
- Migration functions and historical migration tests.

No new flat compatibility layer should be introduced. Legacy code should receive bug fixes only when required for supported compatibility, and no new gameplay features should be added to it.

## Ordered roadmap

### P0 — keep quality protection intact

The current main commit has green CI summary, Ruff, deterministic tests, scoped and repository-wide Pyright, and both CodeQL language checks. Every follow-up PR must start from latest main and remain unmerged until all required checks are green.

### P1 — next implementation sequence

1. **Complete combat attack-profile extraction.** Move player/NPC equipment and natural-attack profile resolution into an application collaborator. Keep validation behavior, supported metadata, attack result shape and transaction boundaries unchanged.
2. **Decompose DurableNativeTurnService.** Extract cohesive public lifecycle workflows behind the current service façade. Preserve turn idempotency, campaign revision checks, lease fencing, clarification/manual-roll retries, narration recovery and atomic commit.
3. **Audit CombatEncounterService transactions.** Map writes to encounter snapshots, canonical CharacterState/CreatureState HP and persistent effects. Add failure/rollback tests before moving responsibilities.
4. **Review WorldService.** Inventory transaction ownership and dispatch responsibilities; split only where an operation family already has a clear stable boundary.
5. **Split broad API schemas.** Organize models/schemas.py by bounded context, preserving current router imports through explicit migration or re-export strategy only if needed.

### P2 — navigation and test maintenance

- Keep package READMEs as local entrypoints and the architecture map as global navigation.
- Continue splitting only genuinely mixed test files. Do not remove tests to reduce line counts.
- Refresh test-suite inventories after each test reorganization; the 2026-11-11 large-file table predates the PR #193 test split and should not be treated as a current exact line-count report.
- Keep module improvement notes close to the owning package README and cross-link to the architecture map.

### P3 — defer until justified

- Migration file-level extraction; preserve ordered replay and historical identity.
- Runtime cache eviction or distributed coordination; current support is process-local/single-worker.
- New provider retry/cancellation abstractions; avoid layered hidden retries.

## Acceptance policy

Every implementation PR:
- begins from the latest integrated main;
- has one architectural objective and a coherent scope;
- includes consumer review and regression tests;
- preserves all applicable public contracts and transaction boundaries;
- updates package and global navigation documents;
- passes Ruff, deterministic Python tests, JavaScript tests, required Pyright scopes, repository-wide Pyright and both CodeQL checks;
- reports live provider/manual client checks separately.

Do not merge while a required check is failed, pending, cancelled or skipped.
