# Shared models and contracts

This package contains domain records and immutable value contracts shared across
service boundaries. Keep provider-specific parsing, persistence orchestration
and business workflows outside the model layer.

## Player-language understanding

`player_intent_analysis.py` provides the versioned `PlayerIntentAnalysis`
contract:

- **V1 compatibility:** original category/step/action/target/attribution shape
  remains decodable and serializes back to its original shape.
- **V2:** each step requires a `SemanticActionFrame`; the analysis may also
  carry bounded directed `SemanticRelationClaim` records.
- Both versions preserve ordered steps, active-step and clarification state,
  actor, modality, polarity, player-reported outcome and literal evidence.

`semantic_frames.py` defines untrusted, ID-free semantic value objects:

- `SemanticMention` — exact text and coarse `kind_hint` (character, creature,
  location, item definition/instance, event, faction, resource, world entity or
  unknown). A hint is not canonical identity.
- `SemanticArgument` — a semantic role plus its mention.
- `SemanticActionFrame` — literal predicate, bounded family and typed
  arguments such as agent, patient/theme, recipient, source, destination,
  instrument, location/path, beneficiary, experiencer, owner, holder or
  container.
- `SemanticRelationClaim` — step index, directed subject/predicate/object,
  family hint, polarity, modality, literal source excerpt, optional attribution
  and temporal expression.

`PlayerIntentAnalysis.from_payload()` is the trust boundary for model output.
It rejects unsupported fields/enums, over-budget arrays/text, invalid step
ordering, missing frames in v2, relation claims referencing missing steps,
non-literal source/mentions/predicates/attributions/temporal expressions and
attempts to attach canonical IDs.

The interpretation is language evidence, not authorization. It cannot assign
canonical IDs, permissions, visibility, provenance, dice or write operations.
Application code resolves visible canonical references; world services and
rules remain authoritative for mutation and mechanics.

## Discourse and pending-correction contracts

- `discourse_evidence.py` records where a candidate was mentioned (player input
  or narrator prose), the scoped transcript turn, recency and a bounded excerpt.
  `DiscourseCandidate` carries deterministic application scores and the
  signals that contributed to ranking. These records are produced by
  application code, never accepted from the model.
- `pending_intent_correction.py` defines explicit corrections for a target,
  action argument or directed relation endpoint. Applying one returns a new
  immutable analysis and requires literal player evidence plus an explicitly
  pending, uncommitted resolution. It never edits a committed turn or world row.
- The correction value object is a guarded application primitive. The current
  combined provider schema does not yet emit correction objects automatically;
  this PR does not claim full model-driven correction-chain support.

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
- Preserve v1 decoding whenever evolving v2.
- Add deterministic parser, prompt, codec and lifecycle tests with schema changes.
- Keep untrusted interpretation distinct from confirmed facts and committed
  consequences.
- Update the P0 specification and package guides when semantics or bounds
  change.
