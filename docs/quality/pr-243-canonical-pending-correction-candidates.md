# PR #243 — Canonical pending correction candidates for linked mentions

## Problem

The live correction fixture for a directed relation contains the same mentions in
both `action_frame.arguments` and `relation_claims`. For example, "Mara protege
a Bram" can expose `Mara` and `Bram` as action-argument candidates and again as
relation subject/object candidates.

The typed patch application keeps linked semantic structures synchronized:
editing an action argument also updates matching relation endpoints, while
editing a relation endpoint also updates matching action-frame mentions. The
catalogue therefore offered multiple IDs for overlapping linked edits. This
added choice complexity without giving the model independent changes to make.

## Change

- Relation endpoints are the canonical correction candidates when a mention in
  the same step is also represented by an action-frame argument.
- The overlapping action-argument candidate is omitted; its positional ID is
  not reassigned, so all unrelated argument IDs remain stable.
- Action arguments whose mentions do not occur in relation endpoints remain
  available as candidates.
- Previous-value mismatches now carry safe structured diagnostic metadata:
  selected slot ID/type and, when applicable, the other matching slot ID/type.
- The warning log records only those numeric IDs and backend-resolved slot
  types. It never records previous values, replacement text, excerpts or raw
  provider completions.

## Safety

No selector is guessed, repaired or silently redirected. The model must still
select an available catalogue ID and echo the corresponding current value.
Literal replacement/excerpt validation and typed pending-only application are
unchanged. A rejected response remains rejected.

The relation endpoint is preferred because it retains the narrowest explicit
claim index and endpoint kind; the existing typed patch synchronizes the
corresponding frame mention. The catalogue does not infer argument roles from
relation semantics.

## Deterministic coverage

- A relation analysis with matching agent/patient arguments exposes only the
  relation subject/object slots for those mentions.
- Applying a relation object correction synchronizes the linked action-frame
  argument.
- A non-overlapping action argument remains addressable at its original ID.
- Safe validation logs expose selected/matching IDs and slot types but no
  player/model-supplied text.

The live Ollama holdout remains the acceptance gate for Gemma selection quality.
CI success alone does not establish that the model chooses the right slot.
