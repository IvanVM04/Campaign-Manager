# Pending correction selector inference

## Problem

The live Gemma 4 12B correction holdout reached the correction validator but
rejected three legitimate scenarios:

- An `action_argument` correction supplied a non-null
  `relation_claim_index`.
- A `relation_object` correction supplied a non-null `argument_role`.
- The first round of a two-round `action_argument` correction repeated the
  first mismatch.

The model selected the intended semantic `slot`, but the response contract
asked it to coordinate two additional nullable selector fields. Those fields
are derivable from the stored pending analysis in the ordinary, unambiguous
case.

## Design

The dedicated `INTENT_CORRECTION_RESPONSE_SCHEMA` now asks for only:

- `step_index`
- `slot`
- `previous_value`
- `replacement`
- `source_excerpt`

The `IntentInterpreter` path uses
`PendingIntentCorrection.from_intent_payload()` to resolve the internal
selector from the pending analysis:

- `action_argument`: infer the argument role only when exactly one argument
  in the selected step matches `previous_value`.
- `relation_subject` / `relation_object`: infer the claim index only when
  exactly one endpoint of the requested kind in the selected step matches
  `previous_value`.
- `target_mention`: require exactly one matching target mention.

Zero or multiple matches are rejected. The model is instructed to return
`needs_clarification` when the pending value could refer to more than one
compatible slot. The backend does not guess, normalize into a different
candidate, or weaken literal evidence checks.

The older `INTENT_MECHANICS_CORRECTION_RESPONSE_SCHEMA` and
`PendingIntentCorrection.from_payload()` remain unchanged for the deprecated
combined `MechanicsAdjudicator` compatibility path. This change is scoped to
the current `IntentInterpreter` contract.

## Prompt-size assessment

This is deliberately not solved by adding more prompt text. The interpreter
has a 24,000-byte prompt ceiling and removes optional context sections when
needed. The correction path already omits duplicated history and uses the
pending semantic snapshot plus the latest answer. The JSON schema is sent
separately in Ollama's `format` field, so prompt-byte telemetry does not
measure schema size.

The observed failure is a contract-shape error, not evidence of context-window
exhaustion. The response contract is therefore simplified instead of extended.

## Safety invariants

- Replacement mentions and correction excerpts must remain literal in the
  latest player answer.
- The pending step and requested slot must exist.
- The previous value must identify exactly one compatible stored slot.
- Multiple candidates are rejected rather than resolved heuristically.
- Corrections remain limited to uncommitted pending intent; they do not
  authorize mechanics or world writes.
- The existing deterministic `apply()` path remains responsible for the
  actual patch and untouched fields remain preserved.

## Validation status

Deterministic tests cover inferred argument roles, inferred relation indexes,
ambiguous matches, and rejection of legacy selector fields in the compact
Intent contract. Live Ollama acceptance must be rerun after this change; the
previous live run is a failure baseline, not a passing result.
