# Character services

## Responsibility
Character creation, character state use cases and application of validated character mutations.

## Modules
- `character_creation_service.py` — creates the entity and CharacterState and optionally activates the character.
- `character_service.py` — character-state use cases, currently HP changes.
- `character_sheet_query_service.py` — builds a detached D&D 5e sheet projection, including persisted Hit Dice availability.
- `character_rest_service.py` — performs campaign-scoped short/long rest recovery in one `IMMEDIATE` transaction.
- `character_applier.py` — translates typed character operations into service calls and OperationResult values.
- `__init__.py` — public package exports.

Character state and schemas remain in `models/`, persistence in `repositories/`, and typed mutation commands in `operations/`.

## Dependency rules
- Read projections expose only player-facing fields; never return entity notes or raw character metadata.
- Coordinate use cases through repositories and typed operations.
- CharacterState remains canonical for player-character mechanics, including HP, Hit Dice size/use and the last long-rest campaign-time marker; encounter/equipment values are projections.
- Do not depend on API routers or LLM provider adapters.
- Keep rules-engine mechanics out of these application services.

## Transaction and ownership notes
- CharacterCreationService currently owns its connection via `get_conn()`; this migration deliberately preserves that behavior.
- CharacterService.change_hp accepts an optional connection so turn/world workflows can participate in their caller-owned transaction.
- CharacterApplier remains an adapter from CharacterOperation to CharacterService; it does not own persistence or transactions.
- WorldService currently composes CharacterApplier, so its existing wiring and shared repository identity must remain intact.

## Hit Dice and rest contract

- Migration 030 stores `hit_die_sides`, `hit_dice_used` and
  `last_long_rest_elapsed_minutes` on canonical `CharacterState`.
- The 2014 class Hit Die mapping is deterministic for the twelve core classes.
  Because `class_name` remains free text and multiclass progressions are not
  modelled, unknown/multiclass labels use an explicit d8 fallback; character
  creation does not claim to validate class rules.
- A short rest advances 60 campaign minutes. The player may spend up to the
  available Hit Dice; each die heals `max(0, roll + CON modifier)`, then HP
  is capped at max HP. Dice may be rolled by the app or supplied manually.
- A long rest advances 480 campaign minutes, restores HP to max, and recovers
  up to half the character's total Hit Dice (minimum one, never more than
  previously spent). The one-beneficial-long-rest-per-24-campaign-hours rule
  is measured from the start of the previous long rest.
- Both workflows reject an active campaign combat encounter, compare the
  caller's expected campaign-clock value, expire due campaign-time effects,
  and write the character/resource/clock changes in one
  `transaction("IMMEDIATE")`. A failure rolls back all of them.
- Long-rest interruption by strenuous activity and resources that do not yet
  exist as persisted mechanics (spell slots, class/subclass features, charges)
  are not simulated. Do not store those as generic counters until their
  rules/source-of-truth contracts exist.

## Remaining work

The cross-package sequencing and estimated effort for this package are tracked in the [engineering readiness and gameplay roadmap](../../docs/architecture/engineering-readiness-and-gameplay-roadmap-2026-11-12.md).

- [ ] Build a typed class/race/background character builder and validate level,
  proficiency and HP progression once those concepts have explicit models.
- [ ] Add typed spellcasting and class-feature resources with class-specific
  recovery rules; do not conflate them with generic world ResourceBalance.
- [ ] Add a read-only attack summary to the sheet when its payload can reuse
  the canonical equipped-item/rules-engine profile resolution.
- [ ] Revisit CharacterCreationService transaction ownership separately, with
  explicit caller-connection support if another use case needs composition.
- [x] Expose current ability/skill/save/AC/armor proficiency and Hit Dice sheet
  projections without exposing notes or raw metadata.
- [x] Enforce transport/provider/service dependency boundaries in
  `tests/test_architecture_boundaries.py` and
  `docs/architecture/package-dependency-matrix.md`.
