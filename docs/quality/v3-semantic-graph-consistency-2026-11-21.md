# V3 semantic graph consistency validation — 2026-11-21

**Implementation:** PR #295.  
**Scope:** v3 interpretation decoder and deterministic contract tests.  
**Production authority:** v2 remains the live turn route; v3 is still an opt-in/shadow contract and has no mechanics or persistence authority.

## 1. Problem

Before this milestone, the v3 DTO checked exact current-utterance spans, record-local literal grounding, unique local IDs, and that references resolved to some local record. The graph scorer independently checked that gold event/fact evidence belonged to its declared source act. The strict decoder did not yet enforce the same cross-record invariant on model output.

Consequently, a model could produce valid JSON in which an event or fact cited words elsewhere in the message but claimed to originate from an act that did not contain those words. Some discourse edges could also resolve to real IDs while connecting semantically incompatible endpoint kinds or directions.

PR #295 moves the high-confidence cross-record invariants into the strict v3 decoder. It does not alter the prompt, schema version, graph gold or production route.

## 2. Cross-record evidence ownership

For every event and world-fact candidate:
- `source_act_id` must resolve to an utterance act (existing invariant);
- every child evidence span must be fully contained in one of that act's evidence spans;
- each predicate, argument mention, fact endpoint, value and attribution must still be literal in that record's own evidence spans.

Containment is exact by Unicode character offsets. A span cannot be assembled from two separated parent spans. This prevents a model from borrowing the evidence of another act while retaining a misleading source-act edge.

For every clarification:
- all affected IDs must resolve to an act, event, discourse link or fact (existing invariant);
- each clarification evidence span must be contained in evidence owned by at least one affected record.

This also covers `link_*` targets.

## 3. Typed discourse-edge invariants

The validator enforces only link semantics that are already established by the architecture and current selector:

### `condition_on_success`
- source and target must both be events;
- source is the dependent event; target is its prerequisite;
- the prerequisite must precede the dependent event in source order;
- the dependent event must be in `planned` phase;
- duplicate typed edges are rejected.

This mirrors the existing backend selector/checkpoint contract: a dependent action is not a current attempt and cannot be enabled by a forward or unresolved prerequisite.

### `before_after`
- both endpoints must be events;
- the source event must precede the target event.

### `quotes`
- source must be an utterance act and target an event;
- the target event must declare that same act as its source;
- edge evidence must be contained in one of the source act's literal `quote_spans`.

The edge does not assert that quoted content is true or executable. It only binds a quoted proposition/event to the act that contains it.

### Other link types
They continue to require valid, distinct, same-turn local endpoints and their existing callback rules. PR #295 deliberately does not invent endpoint-direction policies for `reports`, `response_to`, `correction_of`, `elaboration`, `contrast` or `continuation` without a separately agreed semantic contract and reviewed gold examples.

## 4. Fact shape consistency

The existing relation and entity-attribute contracts remain unchanged. The `other` fact kind is now explicitly prevented from carrying relation-only metadata (`relation_family`, `direction`, `normalized_relation_type`); it must still have an object or value surface.

No family-to-normalized-key mapping is imposed here. The current corpus intentionally uses aliases such as `social.hostility` and `social.friendship` for relation families `hostility` and `friendship`; taxonomy canonicalization remains a separately reviewable concern.

## 5. Diagnostics and privacy

Cross-record failures become `TurnInterpretationV3ValidationError` values with stable, content-free codes and field paths, for example:
- `event_evidence_outside_source_act`;
- `fact_evidence_outside_source_act`;
- `condition_dependency_forward_reference`;
- `quote_link_source_act_mismatch`;
- `clarification_evidence_outside_affected_records`.

Diagnostics never include the player's utterance, evidence text, mentions, prompt or completion. No new raw model content is added to logs or reports.

## 6. Deterministic coverage

Tests cover valid and invalid:
- event and fact evidence ownership by their declared source act;
- quote link endpoint kinds, source-act identity and quote-span containment;
- condition event endpoints, dependent/prerequisite direction, source order and planned phase;
- duplicate graph edges;
- before/after source order;
- clarification evidence ownership for affected records;
- relation-only fields on `other` facts;
- content-free decoder diagnostics.

Run:

```powershell
python -m pytest tests/test_player_turn_interpretation_v3.py tests/test_player_turn_v3_graph_evaluation.py tests/test_player_turn_v3_shadow.py -q
ruff check models/player_turn_interpretation_v3.py tests/test_player_turn_interpretation_v3.py
```

## 7. Explicit boundaries

- No v3 schema-version change.
- No prompt or model/provider setting change.
- No fuzzy evidence correction or semantic inference.
- No changes to canonical identity, permissions, visibility, action selection, mechanics, persistence or durable commit.
- No attempt to make every discourse-link type more restrictive than its currently agreed semantics.
- V2 remains production; v3 remains diagnostic/shadow until the separate acceptance milestone.

A malformed or contradictory local graph now fails before it can be passed to the action selector or world-fact policy. A valid graph is still only an untrusted interpretation, not an authorization to act or persist.
