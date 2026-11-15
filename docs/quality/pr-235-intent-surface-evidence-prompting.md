# PR #235 — exact surface evidence for Intent v2

## Triggering live evaluation

The Gemma 4 12B discourse holdout run on 16 November 2026 completed its
44 Ollama requests in approximately 260.69 seconds. The provider requests
completed normally, but the semantic evaluator recorded repeated validation
failures in these fields:

- `steps[].action_frame.predicate` — `evidence_not_in_player_text` and, in
  some cases, `evidence_not_in_step_excerpt`;
- `steps[].target_mentions[]` — the same two evidence-grounding categories;
- `relation_claims[].predicate` — `evidence_not_in_player_text`.

These failures appeared across topic-boundary, callback, ellipsis, reference,
grammatical-agreement and NPC-attribution scenarios.

The live harness deliberately does not log raw completions or rejected values.
Therefore the exact strings emitted by Gemma are not available in this report.
A likely explanation for some predicate failures is verb lemmatization or
normalization (for example, returning an infinitive instead of the written
conjugation), but that remains a hypothesis rather than an observed completion.
The target-mention failures are consistent with replacing a current pronoun
with a history-derived entity name, or with choosing a source excerpt that
does not include all mentions; those causes also need confirmation from later
measurements.

## Contract clarification

The v2 model validator already enforces literal evidence; this PR does not
change that enforcement. It makes the generation instructions and schema
descriptions precise about what the model must emit:

1. **Verbatim surface predicate.** `action_frame.predicate` and
   `relation_claims[].predicate` preserve the exact written form, including
   conjugation, person, tense, number, clitics and accents. No lemmatization,
   infinitive conversion, translation or synonym substitution.
2. **Contiguous source excerpt.** A step's `source_excerpt` is one continuous
   substring of the current player message. It must include the predicate and
   all mentions used by that step. For a callback, it must include both the
   callback phrase and its action/question clause.
3. **Surface mentions remain unresolved.** Target mentions, typed action
   arguments and relation endpoints are copied as written. Pronouns and
   demonstratives stay as pronouns/demonstratives; the model must not replace
   them with names recovered from history.
4. **Contextual action description is separate.** The `action` field may
   summarize an action recovered from a unique, visible and pending antecedent.
   That semantic description is not evidence for the predicate, mention or
   source-excerpt fields.
5. **Ellipsis stays grounded.** When the current turn has no lexical action
   verb, the model uses the shortest literal expression that signals the
   ellipsis as its evidence anchor; it must not import the previous turn's verb.

The normal Intent prompt, correction prompt and structured JSON Schema now state
these distinctions. The model/domain decoder remains strict. No evidence field
is silently repaired, no history text is copied into current-player evidence,
and no resolver or world-mutation rule is relaxed.

## Deterministic coverage

A new deterministic contract test asserts that:
- the normal prompt says to preserve the exact surface form, not lemmatize,
  keep pronouns/demonstratives and use a contiguous excerpt;
- the correction prompt repeats the same grounding rules;
- the structured schema describes literal mention text, predicate forms,
  complete source excerpts and the separation between semantic `action` and
  literal evidence.

These tests verify the prompt/schema contract only; they do not claim that a
particular local model follows it.

Run:

```powershell
python -m pytest tests/test_modular_language_pipeline.py -k "surface_evidence or prompt" -q
python -m pytest tests/test_intent_validation_diagnostics.py tests/test_semantic_frames.py tests/test_player_intent_analysis.py -q
```

## Acceptance after merge

Repeat the focused held-out examples and then the full 24-scenario discourse
evaluation with the same pinned model. Compare validation failures by field
and family, and inspect semantic slot recall only after the corresponding
Intent payload has passed strict decoding.

A reduction in evidence-grounding failures is the immediate acceptance signal.
It is not sufficient on its own: category accuracy, action-frame roles,
reference resolution, abstention and the broader held-out corpus must still be
measured independently.
