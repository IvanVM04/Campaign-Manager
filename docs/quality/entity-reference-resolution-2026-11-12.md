# Entity reference resolution — 2026-11-12

**Implementation branch:** `feat/entity-reference-resolution`.

## Purpose

Context retrieval must not attach a player intent to an arbitrary entity merely because one word in a long query appears in its notes. Identity matching is a separate, deterministic collaborator with an explicit result: `resolved`, `ambiguous` or `unresolved`.

## Identity data contract

- `Entity.name` is the canonical name.
- `Entity.aliases` contains at most 20 explicit, durable alternate names; each alias is at most 100 characters.
- Aliases are trimmed, case-insensitively deduplicated and never duplicate the canonical name at the domain boundary.
- Aliases are supplied through bootstrap/API or typed world operations. The resolver never promotes description or notes text into a stored alias.
- Migration 031 adds `entities.aliases` as JSON text with `[]` as the legacy default. It does not guess historical aliases.
- API bootstrap, entity read projections, repository serialization and the LLM operation schema use the same field.

Aliases do not have independent secrecy or provenance semantics. Do not treat this field as a GM-only channel; the current world visibility model does not provide entity-level alias visibility. This PR does not alter that contract.

## Matching policy

The resolver normalizes case, diacritics, punctuation and whitespace. It considers only active entities with integer IDs.

| Evidence | Priority | Rule |
|---|---:|---|
| Canonical name | Highest | All significant name tokens must be present in the query; a complete phrase has the strongest score. |
| Explicit alias | High | All significant alias tokens must be present; explicit domain evidence outranks free text. |
| Description | Medium | Every significant query token must occur in the same entity description. |
| Notes | Low | Same all-token rule, only as a compatibility fallback. |

Ambiguity policy:

- A canonical name or alias shared by multiple active entities is ambiguous.
- Similarly scored descriptive matches are ambiguous.
- An ambiguous result exposes candidate information to internal projection diagnostics but returns no selected entity IDs to memory search.
- Multiple distinct, explicitly mentioned names/aliases can resolve to multiple entities.
- No substring-in-token or one-word-of-many matching is used for entity identity.

## Prompt behavior

The proposal projection records reference status, match kind and candidate count without copying the raw query into diagnostics. When a reference is ambiguous, the LLM context renderer instructs the proposal model not to choose an entity, mutate a candidate or create a duplicate to work around the ambiguity.

The resolver does not mutate the world, decide game mechanics, call a model, access SQLite or depend on an embedding service.

## Limits and follow-up

This is not full coreference resolution:

- isolated pronouns such as “él”, “ella” and “eso” are not resolved;
- cross-turn speaker identity, recency and point-of-view are not represented by the alias resolver;
- translated synonyms and broad semantic paraphrases are not guaranteed;
- location and item nicknames need separate typed evidence if a labeled evaluation set demonstrates a gap.

These cases belong in later intent/history evaluation. Do not introduce embeddings or a vector database until a representative, labeled corpus demonstrates a material recall/precision improvement over explicit domain data and deterministic matching.

## Test matrix

The deterministic suite covers canonical and alias hits, case/diacritic normalization, role-description matching, multiple explicitly mentioned entities, alias collisions, ambiguous roles, inactive entities, parser/API validation, repository round-trip, migration idempotency and proposal-prompt abstention.
