# Atomic selectors for pending intent corrections

## Problem

The live Gemma 4 12B correction holdout reached the correction validator but
rejected three legitimate scenarios:

- An `action_argument` correction supplied a non-null
  `relation_claim_index`.
- A `relation_object` correction supplied a non-null `argument_role`.
- The first round of a two-round `action_argument` correction repeated the
  first mismatch.

The model selected the intended semantic slot, but the response contract
asked it to coordinate two separate nullable selector fields. This allowed
mutually irrelevant selector metadata to be populated at the same time.

## Design

The dedicated `INTENT_CORRECTION_RESPONSE_SCHEMA` asks for five fields:

- `step_index`
- `slot`
- `previous_value`
- `replacement`
- `source_excerpt`

The `slot` is a single discriminated identifier:

- `target_mention`
- `action_argument:<role>`, for example `action_argument:recipient`
- `relation_subject:<index>`, for example `relation_subject:0`
- `relation_object:<index>`, for example `relation_object:0`

The schema enumerates the supported argument roles and relation indexes.
The backend parses the selector and verifies that the selected argument or
relation endpoint exists on the stated step and contains the exact
`previous_value`. Separate `argument_role` and `relation_claim_index`
fields are not accepted by this Intent contract, so contradictory auxiliary
selectors cannot be returned.

A valid selector is still subject to literal replacement/excerpt validation
and deterministic application. Unknown roles, missing indexes, stale steps,
wrong endpoint values, extra fields and malformed selectors are rejected.
The older `INTENT_MECHANICS_CORRECTION_RESPONSE_SCHEMA` and
`PendingIntentCorrection.from_payload()` remain unchanged for the deprecated
combined `MechanicsAdjudicator` compatibility path.

## Prompt-size and context assessment

This is deliberately not solved by adding more prompt text. The interpreter
has a 24,000-byte prompt ceiling and removes optional context sections when
needed. The JSON schema is sent separately in Ollama's `format` field, so
`prompt_bytes` telemetry does not measure schema size.

The correction path bypasses fresh world-context retrieval and the discourse
index. Its pending-state projection contains only candidate target mentions,
action arguments and relation endpoints. The action description/source
excerpt and current DM question remain available, while actor, modality,
outcome, attribution, temporal details and unrelated world context are not
repeated to the correction model. The latest player answer is not duplicated
inside the pending-state JSON.

The observed failure was a response-contract coordination problem, not
evidence of context-window exhaustion. The fix therefore makes the slot
selector atomic instead of extending the prompt.

## Safety invariants

- Replacement mentions and correction excerpts remain literal in the latest
  player answer.
- The step, selector kind, role/index and previous value must all match the
  stored pending analysis exactly.
- The model cannot choose two competing selector fields.
- Invalid or ambiguous selectors are rejected; the backend never guesses.
- Corrections remain limited to uncommitted pending intent and do not
  authorize mechanics or world writes.
- `PendingIntentCorrection.apply()` remains the only patch application path;
  untouched fields are preserved.

## Validation status

Deterministic coverage includes action-argument and relation endpoint
selectors, repeated mentions disambiguated by explicit role, mismatched
selectors, nonexistent relation indexes, rejection of legacy selector fields,
and correction-context isolation. Live Ollama acceptance must be rerun after
this change; the previous live run is a failure baseline, not a passing result.
