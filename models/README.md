# Shared models and contracts

This package contains immutable and mutable domain records shared across
service boundaries. Keep provider-specific parsing, persistence orchestration
and business workflows outside the model layer.

## Language-understanding contract

- `player_intent_analysis.py` — versioned schema v1 for an untrusted semantic
  interpretation of one player utterance.
  - `PlayerIntentAnalysis` stores utterance category, ordered steps, the
    currently active step and optional clarification state.
  - `IntentStep` distinguishes actor, action, modality, polarity,
    player-reported outcome, exact literal target mentions and attribution.
  - `from_payload()` is the strict trust boundary for model output. It rejects
    unsupported fields/enums, excessive steps/targets, non-contiguous order,
    invented source excerpts/target mentions, invalid active-step transitions
    and a reported result that is still marked active. Conversation context and
    player-authored evidence are distinct inputs: DM clarification questions
    can explain an answer but can never be cited as the player's words.
  - `is_actionable` is intentionally narrower than "contains an action":
    only a current, positive player attempt without an already-reported result
    is eligible for mechanics adjudication.
  - `allows_world_proposal` is a proposal gate, not write authorization.
    Canonical entity identity, visibility, provenance, permissions, dice and
    domain validity remain owned by their existing deterministic boundaries.
  - `unrecognized()` returns a no-step clarification state when a production
    provider omits the v1 contract. The durable production path fails closed.
  - `conservative_legacy()` is retained only for the legacy `adjudicate()` API
    and old fixtures. It is not used by the durable production turn pipeline.

The model cannot assign canonical entity IDs or write-operation payloads.
Literal mention strings are retrieval evidence only. Deterministic reference
resolution may select a unique visible target; ambiguity must remain
unresolved and be clarified rather than guessed. PR #216 adds
`resolved_conversation_reference.py`, a trusted application-produced match
that records the literal mention, canonical visible entity and optional
antecedent turn. The model never constructs this record or supplies its ID.

The v1 contract still lacks typed semantic arguments, relation assertions,
object-kind hints and structured correction links. Those require a new schema
version, not a silent change to persisted v1 interpretations.

The language pipeline is coordinated in `services/turns`: the mechanics
adjudicator returns this analysis together with the mechanics decision in one
provider response, and the exact object is passed into the world proposal
prompt. The model package remains independent of providers, services and
SQLite.

## Related durable contracts

- `turn_resolution_record.py` — durable in-flight resolution and its JSON
  evidence, including the versioned `intent_json` field.
- `turn_record.py` — historical transcript record; do not conflate it with
  the durable resolution lifecycle.
- `turn_context.py` — detached inputs to a turn; do not use as an unbounded
  service locator.
- `world_context_projection.py` — bounded detached context for the model;
  selection and rendering remain separate responsibilities.

## Change rules

- Version the semantic schema; never silently reinterpret a persisted schema.
- Add deterministic parser and lifecycle tests with schema changes.
- Keep untrusted interpretation distinct from confirmed facts and committed
  consequences.
- Update the P0 specification and package guides when semantics or bounds
  change.
