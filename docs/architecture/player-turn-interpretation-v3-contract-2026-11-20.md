# Player turn interpretation v3 — contract proposal

**Date:** 2026-11-20  
**Implementation PR:** #285  
**Architecture source:** [Player-intent semantic redesign audit — PR #282](player-intent-semantic-redesign-audit-2026-11-20.md)  
**Current production contract:** `PlayerIntentAnalysis` v2  
**Status:** v3 DTOs and strict deterministic decoder are implemented for contract validation only. They are **not wired into the production prompt, interpreter, mechanics, proposal, durable-resolution or persistence paths**.

## 1. Purpose and scope

PR #282 identifies that v2 uses one step/modality structure for several different semantic planes: communicative force, event content, epistemic status, action phase, discourse continuity, playable intent and write authority. PR #284 addressed the narrow immediate v2 defects. The next audit phase is to define and validate a new versioned representation without changing production behavior.

This document records the v3 contract delivered by PR #285. It closes the phase-1 design questions with a deliberately bounded MVP vocabulary, rather than attempting a universal linguistic ontology.

In scope:

- immutable, typed records for utterance acts, event/proposition frames, discourse links, world-fact candidates, clarification candidates and evidence spans;
- strict model-payload decoding, local-reference integrity and source-span validation;
- a separate backend-only value object for derived gameplay-action candidates;
- deterministic unit/contract tests and a production-isolation regression.

Out of scope:

- changing the Intent prompt or response schema used in production;
- running v3 in shadow mode or comparing v2/v3 model output (PR #286);
- changing which action is adjudicated, adding an action selector or dependency checkpoint (PR #287);
- persisting v3 or fact candidates, changing migrations, codecs or durable lifecycle;
- changing LLM provider roles, model settings, number of calls or context selection;
- adding a syntactic parser, Stanza dependency, vector database or additional service.

The purpose is to validate whether the model and backend can express the separate semantic objects safely before asking a live model to produce them.

## 2. Contract boundaries

The model-facing top-level payload is `TurnInterpretationV3` and has exactly these fields:

- `schema_version`, fixed to integer `3`;
- `utterance_acts[]`;
- `events[]`;
- `discourse_links[]`;
- `world_facts[]`;
- `clarification_candidates[]`.

Unknown and missing fields are rejected. Collection and text bounds are enforced in the decoder. The contract is evidence, not truth, authority or a set of write instructions.

The payload intentionally does **not** contain:

- canonical entity/item/resource/event IDs;
- permissions, visibility decisions or persistence authorization;
- mechanical outcomes, dice results or a selected rules action;
- a model-selected active step/action;
- a historical transcript turn ID or canonical callback target;
- a durable checkpoint or operation list.

The single v3 interpretation remains holistic: acts, events, links and facts are returned in one coherent response. They are not split across separate model calls.

## 3. Semantic records

### 3.1 UtteranceAct — what the speaker is doing communicatively

Each act has a local ID, an `UtteranceForce`, a `SpeakerRole`, optional literal speaker/addressee mentions, quote spans and evidence spans.

The MVP forces are:

- `assertion`, `question`, `in_character_dialogue`, `warning`;
- `request`, `refusal`, `correction`, `hypothesis`, `report`;
- `other`, `unknown`.

`SpeakerRole` is `player`, `npc`, `other` or `unknown`. It is distinct from a speaker mention and from the event agent. A speaker mention remains literal text; it is not a canonical NPC identity. The addressee is also a mention, not proof that the target is known or visible.

Quote spans are nested inside the act's evidence. Quoted text is content of the utterance; it does not become an instruction to the application and does not itself establish that the quoted proposition is true.

### 3.2 EventFrame — what happened, is attempted, or is asserted

An event has a local ID and a source act ID. It stores:

- literal `predicate_surface`;
- an existing bounded `SemanticActionFamily`;
- existing role-labelled `SemanticArgument` values and literal `SemanticMention`s;
- `polarity` independently of epistemic status;
- `epistemic_status`: `asserted`, `observed`, `reported`, `rumor`, `hypothetical`, `uncertain` or `not_established`;
- `action_phase`: `planned`, `attempted`, `ongoing`, `completed`, `state`, `not_applicable` or `unknown`;
- optional literal temporal expression and attributed source;
- exact evidence spans.

Reusing the existing semantic action family and argument-role types avoids creating a second competing vocabulary for the same roles. The important change is that communicative force, factual status and event phase no longer compete for one enum.

A player-reported success or failure remains a claim in the interpretation. When game mechanics are required, only the rules workflow determines the authoritative outcome.

### 3.3 DiscourseLink — how records relate

Links have a local ID, a source local reference, a target local reference when applicable, a type and evidence spans.

The initial link types are `before_after`, `continuation`, `condition_on_success`, `response_to`, `correction_of`, `elaboration`, `contrast`, `reports`, `quotes` and `callback`.

For ordinary links, both endpoints must resolve to records in this same turn. The direction is meaningful: for example, a `condition_on_success` link points from the conditional consequence to the event whose success it requires; a `response_to` link points from the response act to the act it answers.

A callback is intentionally different. It has no local target and carries only a literal `anchor_candidate` supported by current-turn evidence (for example, the phrase naming the wall being revisited). The model cannot select a historical turn, invent a turn ID or resolve a canonical entity. The existing deterministic discourse/reference collaborators remain responsible for selecting a bounded same-chat antecedent and resolving any visible referent.

A callback is a discourse link, not an event by itself.

### 3.4 WorldFactCandidate — a possible durable fact, not a write

A fact candidate records a possible relation, entity attribute or other fact with:

- source utterance-act ID;
- subject mention and, where relevant, object mention;
- literal predicate surface;
- optional namespaced normalized relation key;
- existing relation-family hint and explicit direction;
- polarity, epistemic status, temporal scope and optional attributed source;
- literal evidence spans.

Relation facts require both endpoints, a relation-family hint and direction. The MVP can describe a symmetric relationship explicitly without losing its two endpoints. Entity-attribute facts use a literal value surface and do not masquerade as a relation.

The normalized relation key is a bounded, namespaced string such as `kinship.sibling`; it is not a canonical world ID and does not introduce a closed global taxonomy in this phase. The literal `predicate_surface` remains available for evaluation independently of the normalized concept.

A `WorldFactCandidate` is never a persistence decision. A temporal scope of `permanent` is a semantic claim, not authorization. The future policy must still assess evidence, attribution, stability, visibility, identity, duplicates, domain rules and campaign authority. That policy and the resulting world operations belong to PR #288, not to this DTO.

### 3.5 ClarificationCandidate — what remains ambiguous

A clarification candidate references one or more local records and identifies the ambiguity kind, missing slot, question intent and evidence. It is only a semantic description of ambiguity.

It does not create or mutate a durable resolution checkpoint. Continuation and selective recomputation are part of the later action/dependency milestone and the existing durable lifecycle remains unchanged.

## 4. Evidence and identity rules

### Evidence spans

Every span points to the exact current player input and uses a half-open range `[start, end)` in Python Unicode code-point indices. The decoder verifies:

`source_text[start:end] == text`

These are not UTF-8 byte offsets and not offsets in a concatenated transcript. A span must be non-empty, bounded and use source `current_utterance`. History and narrator prose can help the deterministic discourse resolver, but cannot be promoted into current-player evidence.

Fields such as predicate surface, event arguments, speaker/addressee mentions, fact endpoints, attribution and callback anchors must be supported by the evidence spans of their own record. The model cannot attach an `entity_id` or other canonical identifier to a mention.

### Turn-local identifiers

The decoder requires bounded, typed local namespaces:

- `act_...`, `event_...`, `link_...`, `fact_...`, `clarify_...`;
- backend action candidates use `action_...`.

Local references are unique across a turn and must resolve to the declared record type. They are not database IDs and must never be persisted as canonical identity.

### Canonical references

Only the backend-derived `GameplayActionCandidate` can hold trusted canonical references, represented by `GameplayResolvedReference`. That value is not accepted by the v3 payload decoder. The reference resolver remains responsible for visibility, ambiguity, category and ID checks.

## 5. GameplayActionCandidate — backend-derived, never model-supplied

The audit's `GameplayActionCandidate` is a separate immutable record for trusted backend processing, not part of `TurnInterpretationV3`.

It records the source event, actor mention, supported action type, eligibility, reason, workflow, unlock condition, processing state, target mentions, dependency event IDs and resolved canonical references.

The typed enums distinguish eligibility (`eligible`, `ineligible`, `requires_clarification`, `blocked_by_dependency`), reason, workflow (`none`, `dialogue`, `mechanics`, `clarification`), unlock condition and processing state.

This PR defines the record and its invariants; it does not implement the selector, adjudication routing, dependency state machine or durable checkpoint. The model cannot emit this object or choose the action that production executes. Those responsibilities remain backend-owned and are the subject of PR #287.

## 6. Bounds and strict decoding

The implementation defines fixed collection limits:

| Record | Maximum |
|---|---:|
| Player source text | 20,000 characters |
| Utterance acts | 8 |
| Event frames | 12 |
| Discourse links | 16 |
| World-fact candidates | 12 |
| Clarification candidates | 8 |
| Evidence spans per record | 4 |
| Quote spans per act | 4 |
| Event arguments | 12 |
| Local identifier | 32 characters |

Individual textual fields also have explicit limits. The decoder rejects malformed JSON, unsupported schema versions/enums, unknown fields, wrong types, oversized collections, invalid source offsets, non-literal mentions, broken local references, duplicate IDs and inconsistent relation/attribute shapes. Its public error exposes a fixed diagnostic code and field path rather than model text or raw payload content.

The limits are phase-1 safety bounds, not a claim that every maximum should be used by a live prompt. Phase 2 must measure the actual payload size and model reliability before production.

## 7. Compatibility and rollout

- `PlayerIntentAnalysis` v1 and v2 remain the durable production contracts.
- Existing v1/v2 decoding, encoding, replay and correction behavior is unchanged.
- The v3 module is an additive model-layer contract. No service, bootstrap or integration imports it in this PR.
- No database schema, migration, codec, prompt, provider configuration or runtime gate changes.
- The next milestone, PR #286, introduces one holistic v3 prompt and shadow comparison while v2 remains production.
- v3 must not be used for mechanics or persistence until per-family acceptance gates are approved and met.

## 8. PR #285 validation

The deterministic test suite covers round-trip decoding, orthogonal semantic fields, Unicode offsets, quote containment, exact source matching, history-only mention rejection, canonical-ID rejection, local-reference integrity, callback anchors, directed relation requirements, entity attributes, clarification references, backend-only action candidates, bounds, malformed enums/JSON and immutable records.

A separate architecture regression ensures `services` and `bootstrap` do not import the v3 module. Existing v1/v2 tests remain the compatibility gate. CI and its final commit SHA are reported on PR #285; live Ollama and SillyTavern acceptance are not part of this phase.
