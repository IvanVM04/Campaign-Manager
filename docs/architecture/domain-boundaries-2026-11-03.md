# Domain boundaries and state ownership

**Snapshot:** 2026-11-03  
**Baseline:** `main` at `5fbcb86f357350de9b77f386344d7babf6f681c0`

This document defines the ownership boundaries visible in the current implementation and the boundaries future work must preserve. It is not a claim that every domain already has a dedicated Python package.

## 1. Ownership matrix

| Domain / aggregate | Durable owner today | Runtime representation | Main implementation | Boundary rule |
|---|---|---|---|---|
| Campaign | `campaign` table | `CampaignState`, `CampaignScope` | `CampaignStateService`, `CampaignRepository` | Owns campaign identity/configuration and selected pointers; must not own character or encounter mechanics. |
| Session | `sessions` table | Session state in `TurnContext` | `CampaignStateService`, campaign repository | Belongs to one campaign; turn references must remain campaign-scoped. |
| World | World tables | `WorldState` | `WorldService`, `WorldApplier`, world/entity repositories | Owns persistent fictional facts: entities, items, instances, resources, relations and events. |
| Character mechanics | `character_states` plus linked entity | `CharacterState` | `CharacterRepository`, character services/appliers | Owns persistent PC mechanical state. Narrative extraction is not an authorized writer. |
| NPC creature mechanics | `creature_states` plus linked entity | `CreatureState` | `CreatureRepository`, `CombatEncounterService` | Owns persistent NPC HP, AC, abilities and proficiency bonus across encounters. |
| Encounter | encounter tables | `CombatEncounterState`, `CombatantState` | `CombatEncounterService`, `CombatAttackService` | Owns encounter lifecycle, initiative, turn position and combat snapshot. |
| Persistent effects | persistent-effect tables | `PersistentEffect` | `PersistentEffectService`, effect repository | Owns persistent effect identity, source, duration and lifecycle status. |
| Campaign time | campaign clock table | `CampaignClock` | `CampaignClockService`, clock repository | Owns fictional elapsed time; expiry of campaign-time effects is atomic with advancement. |
| Turn history | `turns` table | `TurnRecord`, `TurnResolutionPlan` | `TurnRepository`, turn services | Owns durable turn/version/idempotency metadata, not the canonical world or character state. |
| Ruleset | Not a separate persisted aggregate | Immutable/result objects | `rules_engine/dnd5e_2014` | Calculates mechanics; must not own persistence or call providers. |
| AI DM | Provider-dependent; no durable domain aggregate | prompts, decisions, plans, narrative | DM/adjudication/extraction services | May propose interpretation and world consequences; cannot bypass deterministic validation or persistence. |

## 2. Important ownership distinctions

### World entity versus player character

A player character is represented by a world entity and a separate mechanical record keyed by the entity ID. The entity carries world identity/description; `CharacterState` carries mechanical values such as HP, AC, abilities and proficiencies.

Do not create a second character identity in the combat or AI layer. Resolve references through the entity ID and the owning campaign.

### Character and NPC HP versus encounter combatant HP

A player character's HP is represented in both `CharacterState` and the encounter's `CombatantState` snapshot. An NPC's HP is represented in both `CreatureState` and the encounter snapshot.

The attack path verifies that these values agree before an attack and updates the owning PC or NPC state and encounter snapshot in one database transaction. Treat encounter HP as a synchronized combat projection, not an independent canonical value.

Required invariant:

> For every persisted PC or NPC participating in an active encounter, its owning mechanical record and encounter combatant HP must agree at every committed transaction boundary.

Every future HP mutation must either update all relevant projections atomically or explicitly reject/defer the mutation while an encounter is active. Do not add a second ad-hoc HP writer.

### Persistent effects versus effective conditions

Persistent effects are campaign records attached to entities. Effective conditions are calculated from applicable persistent effects and may be combined with encounter-local condition state.

The persistent effect is the durable source. The effective condition is a projection used by mechanics. Do not persist a derived effective-condition snapshot as an independent truth unless a specific cache/versioning contract is introduced.

### World state versus campaign metadata

`WorldState` contains the mutable fictional-world collections. Campaign metadata and pointers are assembled separately by `CampaignStateService` into `TurnContext`.

A use case needing both must operate on a consistent campaign-scoped context. Avoid reading campaign metadata from one database snapshot and world state from a stale in-memory object.

### Turn record versus committed state

A turn record is an audit/history/idempotency record. It is not a command log that can be replayed blindly. Snapshots are currently used for external-turn version reconciliation; do not assume every turn is a complete event-sourced transition.

## 3. Campaign isolation invariants

1. Every campaign-scoped request must resolve an explicit `CampaignScope`; no implicit fallback to campaign 1.
2. Every repository read/write for campaign-owned data must include campaign scope.
3. Foreign keys and migration-level triggers remain the final guard against cross-campaign references where applicable.
4. A reference from one campaign to an entity, session, character, encounter or effect in another campaign must fail.
5. External turn identifiers and their active versions are unique within a campaign, not globally.
6. Runtime state and locks are campaign-specific.
7. A future background job must carry an explicit campaign ID/scope; it must not rely on request-local `ContextVar` state.

## 4. Mutation authority

| Actor | Allowed responsibility | Must not do |
|---|---|---|
| Player | Declare PC intent and choose actions. | Directly write campaign state or assert a mechanical result. |
| AI DM / adjudicator | Interpret intent, ask for clarification, adjudicate fictional circumstances, propose structured world consequences and narrate. | Write SQLite, invent dice outcomes, bypass domain validation, mutate PC mechanics from prose. |
| Rules engine | Calculate deterministic mechanics from validated inputs. | Call an LLM, access SQLite, choose campaign narrative or persist state. |
| Application use case | Validate authority/preconditions, coordinate rules and domain changes, own transaction boundary. | Delegate invariant enforcement to prompt instructions. |
| Repository / persistence adapter | Load and persist state within a supplied scope/transaction. | Decide game rules or make narrative decisions. |
| API / integration adapter | Validate transport input, call application use cases, serialize stable results. | Contain domain rules or implement an alternate mutation policy. |

## 5. Required invariants for future features

- A player character's mechanical state can only change through trusted application commands whose inputs are verified by the rules engine or an explicitly authorized administrative operation.
- NPC creature HP and combat statistics are owned by `CreatureState`; encounter snapshots must stay synchronized with it at commit boundaries.
- LLM-generated text is untrusted input, even when generated by the configured DM provider.
- A failed multi-operation application leaves both durable and shared in-memory world state unchanged.
- A failed turn commit must not leave the in-memory runtime ahead of SQLite.
- A repeated external turn/version with identical payload is idempotent; a conflicting payload is rejected.
- Regeneration must restore the prior active version's world snapshot and reapply the replacement within one transaction.
- Clock advancement and campaign-time effect expiry are one atomic operation.
- Encounter progression uses expected round/turn values to reject stale commands.
- All cross-aggregate changes (for example character HP plus encounter HP) must be committed atomically.
- Ruleset-specific values and calculations stay inside the selected ruleset module.

## 6. Open ownership questions (must be resolved before expanding scope)

1. **NPC identity and stat blocks:** NPC mechanical state now lives in `creature_states` and is linked to a campaign entity. Manually supplied encounter participants create a durable NPC; later encounters can reference it using `creature_id`. The encounter combatant remains a synchronized projection. Full NPC action/attack resolution is a separate future feature.
2. **Non-encounter conditions:** persistent effects already have entity ownership, but temporary conditions measured in rounds/turns need a lifecycle model that does not depend on an active encounter existing.
3. **Equipment ownership (resolved by PR #38):** `item_instances.owner_id` is the sole canonical physical-ownership field. `equipped_items` is a campaign-scoped character projection keyed by slot; it cannot transfer ownership, and database constraints require an active item owned by that character in the same campaign. Ownership changes, deactivation and deletion clear the projection. Armor/shield calculations, proficiency restrictions, ammunition consumption and NPC equipment remain follow-up mechanics.
4. **Turn lifecycle:** decide whether narration is a pre-commit plan artifact or a post-commit projection of a committed result. The target architecture should choose the latter for reliable retries, but the migration must preserve SillyTavern compatibility.
5. **AI consequence authority:** define which world fields the DM may propose and which require player confirmation, especially currency, ownership transfers, quest outcomes and irreversible events.

These are design questions, not reasons to stop all implementation indefinitely. Resolve each when the next feature would otherwise make the ambiguity permanent.
