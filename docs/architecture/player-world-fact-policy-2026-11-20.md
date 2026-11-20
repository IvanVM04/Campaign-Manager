# World-fact eligibility and persistence policy — 2026-11-20

## Status and boundary

PR #288 implements the fact-policy building block from the PR #282 semantic
redesign audit, on top of the v3 candidate contract (#285), holistic shadow
interpretation (#286) and durable fact-validation receipts (#287).

The policy in `services/turns/world_fact_policy.py` is a deterministic,
backend-only adapter. It consumes one exact `WorldFactCandidate` from a
validated `TurnInterpretationV3`, trusted `ResolvedConversationReference` endpoint values from the existing
visibility-aware resolver and a detached `WorldState`. It can return at most
one typed world operation. It never calls a model, resolves names, decides
mechanical outcomes or commits state.

**The v3 turn route remains inactive.** This PR does not change the production
IntentInterpreter, proposal prompt, bootstrap, native/SillyTavern orchestration
or historical `intent_json`. The policy is an isolated capability for the
acceptance and integration phase; no claim is made that live turns now use it.

## Eligibility policy

A candidate is eligible only when all of these conditions hold:

- it is the exact candidate contained in the supplied interpretation;
- its source act exists, is player-authored and has assertion force;
- its evidence does not intersect a quoted span;
- it has no attributed source;
- epistemic status is `asserted` or `observed`;
- polarity is positive and temporal scope is permanent;
- every required endpoint resolves to an existing, active world entity;
- each endpoint is a trusted `ResolvedConversationReference` produced by the
  visibility-aware resolver;
- its literal mention matches the exact candidate endpoint, its canonical ID
  resolves to an active entity, and its canonical name matches the world row;
- relation facts have an allowlisted semantic family and a normalized
  relation type.

The policy rejects reported facts, rumours, hypotheses, uncertain or
not-established claims, negative/uncertain polarity, temporary/unknown
temporal scope, quoted instructions and unsupported relation families.
Unknown values do not get promoted by confidence scores or prompt wording.

## Operation mapping

### Entity attributes

A positive, permanent attribute for an existing visible entity becomes an
`UpdateEntityOperation` that appends a concise `predicate: value` line to
`notes`. Existing notes are preserved. An already-present line is reported
as `ALREADY_PRESENT` and does not create another operation.

This mapping is deliberately append-only. It does not rewrite descriptions,
infer entity types, create entities, or overwrite prior notes. Entity creation
remains subject to the existing operation contract, including mandatory,
non-empty `entity_type` validation in `OperationParser`.

### Relations

A relation requires two distinct, visible, active canonical entities, an
allowlisted family, a normalized relation key and explicit direction.
`OBJECT_TO_SUBJECT` reverses endpoints; symmetric relationships canonicalize
the endpoint order. A deterministic relation ID is derived from the canonical
endpoints and normalized relation type.

The operation metadata retains the candidate ID, source act, exact candidate
digest, literal predicate, family, direction, epistemic/temporal status and
evidence spans. Existing active relations are idempotent no-ops. An inactive
matching deterministic relation is reactivated; a conflicting ID is rejected.

Transfer events do not prove ownership or possession. If an ownership or
possession candidate shares its source act with a transfer event, the policy
rejects it. The transfer itself remains an event/action concern; it cannot be
silently promoted to a durable relationship.

## Decisions and durable receipts

The policy returns one of:

- `ACCEPTED`: one backend-generated operation is ready for the normal world
  application/commit boundary;
- `ALREADY_PRESENT`: the fact is already represented and no operation is
  emitted;
- `NEEDS_CLARIFICATION`: a required endpoint is unresolved; the receipt stays
  pending;
- `REJECTED`: an authority, evidence, stability, identity or domain check
  failed; no operation is emitted.

`evaluate_world_facts()` evaluates every candidate independently in source
order; a rejected candidate does not erase another candidate's eligibility.
`FactDecision.to_receipt()` binds each result to canonical JSON and SHA-256 of
the exact candidate. The receipt uses the existing PR #287
`FactValidationReceipt` codec and can be advanced through the checkpoint's
lease-fenced compare-and-swap persistence. A validated receipt means the
candidate passed this eligibility policy; it is not itself a world write or
proof that a commit succeeded.

Operations still go through `WorldService`/`WorldApplier` and the durable
turn commit boundary. The policy does not bypass transaction ownership,
campaign revision checks or post-commit immutability.

## Atomicity and failure isolation

Fact evaluation is independent of action selection and mechanics outcomes.
A failed action must not cause a fact candidate to be reinterpreted as an
action, nor should a reported/failed action manufacture a fact.

The policy emits fact operations separately from action candidates. Callers
must preserve that separation when assembling the durable proposal/commit:
a rejected fact must not discard unrelated valid facts, and an unrelated
mechanics failure must not be treated as evidence against an independently
observed fact. The current PR deliberately does not wire this v3 capability
into the production v2 turn path; end-to-end commit orchestration and live
acceptance remain PR #289 work.

## Deterministic tests

`tests/test_world_fact_policy.py` covers:

- explicit permanent kinship and deterministic relation IDs;
- directed relation endpoints;
- preserving NPC details by appending notes;
- report/rumour/hypothesis/uncertainty, attribution, quote, negation and
  temporary-scope rejection;
- trusted speaker/act requirements;
- visibility-aware resolution, unresolved endpoints and mention-to-ID binding;
- transfer-versus-ownership separation, including separately evidenced explicit ownership;
- independent evaluation of multiple facts in one utterance;
- duplicate idempotency, inactive relation reactivation and exact-candidate
  receipt binding.

No Ollama or SillyTavern behavior is claimed by these deterministic tests.
