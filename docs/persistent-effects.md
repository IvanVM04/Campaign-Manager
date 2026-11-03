# Persistent campaign effects

Persistent effects belong to campaign entities, not combat encounters. They remain stored when an encounter is completed and can target any persisted entity (player characters, NPCs, creatures, or other world entities).

## Supported records in this increment

- `condition`: one canonical D&D 5e (2014) condition from the rules engine.
- `exhaustion`: a level from 1 to 6.
- `narrative`: a campaign-specific narrative state with a simple key and no arbitrary mechanical modifiers.

Effects can be `active`, `suspended`, or `removed`. Removed records are retained for audit/history and cannot be reactivated; apply a new effect instead. Multiple sources may create separate records for the same condition. The later rules integration will project active records into the existing `ConditionSet`.

## Duration and time

This increment supports `permanent` (until explicitly removed) and `conditional` (until a described event is adjudicated and explicitly removed). The condition text is descriptive; it is not automatically evaluated.

Campaign-time, round-based, and turn-based expiration are deliberately not accepted yet. The application does not have an authoritative campaign clock or a complete effect/turn integration. Those duration types must not be represented as if they expire automatically.

## Sources and scope

An effect records a source category, optional source entity, and optional reference string. Target and source entities must belong to the same campaign. Database triggers enforce that boundary even when writes bypass the service layer.

This API persists and manages effect records. It does not yet apply their mechanical consequences to combat, checks, saving throws, exploration, or social resolution; that is the next integration increment. Narrative effects never accept arbitrary mechanical payloads.
