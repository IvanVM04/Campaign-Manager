# Backend-generated pending correction slot catalogue

## Context

The live Ollama correction holdout continued to expose selector errors after
PR #241. The model had to reconstruct a compound selector (step, slot kind,
role or relation index) and repeat the stored value. In the relation case it
could choose an inconsistent endpoint/value pair even though both endpoint
values were already present in the prompt.

The correction flow now asks the model to select one backend-generated
`slot_id` from an explicit catalogue. The backend resolves the slot type,
step, role, array position or relation claim index from the pending analysis.
The provider no longer reconstructs those fields.

## Catalogue design

`build_pending_correction_candidates()` builds bounded candidates from the
stored pending analysis:

- Target mentions use their target-list position (0-5) within a reserved
  per-step range.
- Action arguments use the same per-step range after the target positions,
  preserving the argument's exact position (0-11) and role.
- Relation subject/object endpoints use a separate range after all step slots,
  preserving the relation-claim index and endpoint kind.

The current limits are eight steps, six target mentions per step, twelve
arguments per step and eight relation claims. The resulting IDs are unique
within a pending analysis and remain position-stable as corrections replace
text values. The JSON schema allows the bounded numeric interval; the backend
rejects IDs that are not actually present in the current catalogue.

The prompt keeps the existing step and relation structure and adds IDs
inside its semantic fields. Each step has
`correction_slots.target_mentions` and
`correction_slots.action_arguments`; each candidate contains only its ID and
current value, plus the argument role when applicable. In a relation claim,
the `subject` and `object` values are objects containing their ID and current
value. The parent step or relation supplies the context, so the prompt does not
repeat the step index, claim index or slot kind on every candidate.

Generic `target_mention` candidates are omitted when the same normalized
mention is already represented by an action argument or relation endpoint.
The typed candidate is more precise: applying the broader target patch can
also update linked semantic-frame references. Duplicate generic target
mentions are omitted because the patch contract cannot address one occurrence
independently. Action arguments sharing a role and normalized value are also
omitted when the current patch implementation cannot uniquely address them.
When an action argument mention is also present as either endpoint of a
relation claim in the same step, the relation endpoint remains the canonical
candidate and the overlapping action-argument candidate is omitted. Applying
a relation-endpoint patch also synchronizes matching action-frame mentions,
so exposing both IDs would offer two selectors for the same linked edit. This
keeps the relation claim index/endpoint as the narrowest available target.
These omissions do not renumber other IDs.

## Response contract and validation

Each correction item contains only:

- `slot_id`
- `previous_value`
- `replacement`
- `source_excerpt`

The model copies `previous_value` from the selected catalogue item and copies
the replacement and excerpt literally from the latest player answer. The
backend:

1. validates the numeric ID and resolves it against a freshly built catalogue;
2. rejects an unavailable ID or a value that does not match the selected
   candidate (including a value that belongs to a different candidate);
3. derives step, slot, argument role and relation index from the candidate;
4. validates literal replacement/excerpt evidence;
5. applies the existing typed patch through `PendingIntentCorrection.apply()`.

Multiple corrections in one response may target distinct IDs. Repeating one
ID is rejected, preventing a second chained edit to a slot that was not
advertised with its post-edit value in the original catalogue. Corrections are
still applied sequentially, so values are checked against the current pending
state and conflicts caused by earlier patches fail closed.

## Safety invariants

- The catalogue is derived only from the existing uncommitted pending analysis.
- The model cannot invent a step, role, relation index or slot type.
- `previous_value` remains an explicit consistency check; the canonical value
  stored in the typed correction is taken from the backend candidate.
- Replacement mentions and correction excerpts remain literal in the latest
  player answer.
- Ambiguous, missing, stale, duplicate or mismatched selections are rejected
  or kept pending for clarification.
- The correction path still bypasses fresh world retrieval and discourse
  indexing; no extra world context is added.
- No prompt-history expansion is introduced. The correction summary changes
  from a list of loosely coupled fields to a compact candidate catalogue.
- No mechanics, world writes, committed intent or unrelated semantic fields
  are authorized by a correction.

## Deterministic coverage

Tests cover:

- decoding recipient and relation endpoint candidates from backend IDs;
- repeated mentions and same-role arguments distinguished by unique IDs;
- stable IDs after a correction changes a value;
- omission of duplicate or structurally represented generic target mentions;
- preservation of target-only fallback corrections;
- rejection of out-of-range/unavailable IDs and values belonging to another
  candidate;
- safe, value-free diagnostic reason codes, including selected/matching
  slot IDs and slot types without logging any mention text;
- relation-endpoint precedence over overlapping action-argument candidates;
- rejection of duplicate IDs in one correction response;
- sequential application of the held-out correction scenarios.

The live Ollama holdout remains a separate acceptance gate. Passing deterministic
CI does not establish that Gemma consistently picks the right catalogue entry.


## Selector mismatch diagnostics

When a selected catalogue ID is available but its echoed `previous_value`
does not match, the validation log now includes only the selected numeric
`slot_id` and its backend-resolved slot type. If the echoed value matches
another candidate in the same step, the log also includes that candidate's
numeric ID and slot type. Mention text, source excerpts, replacements and raw
model completions are never added to these diagnostics.
