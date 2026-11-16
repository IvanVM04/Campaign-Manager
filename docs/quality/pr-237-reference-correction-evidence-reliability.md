# PR #237 — Reference-resolution and pending-correction reliability

## Why this follow-up exists

PR #236 improved some live Intent families, but the 16 November 2026 local
Gemma 4 12B evaluation still exposed two distinct classes of failure:
reference resolution often returned no result even when context retrieval was
complete, and pending-correction re-analysis repeatedly failed strict
evidence validation.

This follow-up deliberately does not add more prompt examples as its primary
intervention. It changes the stage contracts where the current design couples
independent responsibilities.

## Reproducible live evidence

### Discourse / reference holdout

Run on the PR #236 head `83c2d14`
(the local working branch before the test-harness-only follow-up), using:

- Intent model: `gemma4:12b-it-q4_K_M`;
- general model setting: `gemma4:26b`;
- Ollama endpoint: `http://localhost:11434`;
- Ollama CLI version: `0.40.16`;
- Intent thinking: disabled;
- timeout: 900 seconds;
- 28 held-out scenarios, excluding the correction family;
- 44 provider calls, including three repetitions of critical cases;
- pytest wall time: 251.37 seconds.

The provider completed its requests. The corpus failed on semantic and
resolution assertions, not on transport.

#### Before / after the PR #236 baseline

| Metric | Pre-#236 baseline | #236 live run |
| --- | ---: | ---: |
| Context recall | 100% | 100% |
| Intent — local grammatical agreement | 0% | 66.67% |
| Intent — long-distance reference | 0% | 90% |
| Intent — NPC quoted-speech attribution family | 30% | 70% |
| Intent — ellipsis / pending action | 50% | 25% |
| Intent — explicit callback | 25% | 0% |
| Intent — topic boundary | 50% | 50% |
| Resolution — local grammatical agreement | 25% | 8.33% |
| Resolution — long-distance reference | 30% | 20% |
| Entity-link recall | 14.29% | 0% |
| Semantic-slot precision | 68.75% | 93.75% |
| Semantic-slot recall | 57.89% | 78.95% |
| Semantic-slot F1 | 62.85% | 85.72% |
| Correct / incorrect abstentions | 15 / 0 | 15 / 0 |
| Critical false persistent changes | 0 | 0 |
| Secret leaks | 0 | 0 |

The semantic-slot F1 improvement is real, but it does not mean the pipeline is
ready. The strongest negative signal is the separation between context recall
(100%) and entity-link recall (0%): candidate retrieval is succeeding while
the next stage is not producing usable links.

### Discourse failure patterns

The live run reported, among others:

- `dp-distance-boundary-13`: expected entity 1301, observed no link; the
  action-frame theme also differed only by the article (`el mapa` vs
  `mapa`), but the argument contract currently compares exact surface forms.
- `dp-distance-outside-window-14` and `dp-distance-equal-focus-16`: expected
  clarification, received neither a resolved reference nor a clarification.
- `dp-grammar-explicit-local-17`: expected `dialogue`, observed `report`;
  no reference to expected entity 1307 was returned.
- `dp-grammar-name-no-inference-18`: category was unstable across repetitions
  (`report` twice, `action` once); expected unresolved pronoun should trigger
  clarification.
- `dp-grammar-contradictory-local-19` and
  `dp-grammar-plural-abstention-20`: expected abstention/clarification but
  received neither.
- `dp-npc-ambiguous-alias-22`: expected a question to the DM, observed
  `report`.

Non-critical mismatches also include dialogue/report classification,
callback handling, ellipsis recovery, and ungrounded relation fields:
`dp-topic-history-segment-02`, `dp-topic-quoted-marker-03`,
`dp-callback-mara-05`, `dp-callback-lighthouse-06`,
`dp-callback-earlier-07`, `dp-callback-not-explicit-08`,
`dp-ellipsis-repeat-09`, `dp-ellipsis-same-10` and
`dp-ellipsis-continue-11`.

The evaluation also reported strict decoder rejections for
`relation_claims[].step_evidence`, `relation_claims[].predicate` and
`relation_claims[].object`. These are not Ollama transport failures.

### Pending-correction holdout

The first correction run on commit `83c2d14` was invalid as a benchmark run:
the fixture used slot `relation_endpoint`, while the synthetic pending-state
helper only recognized `relation_object`. The helper consequently built a
fictional transfer action from an unrelated protection sentence, and the
domain evidence validator correctly rejected it before the second scenario
reached the provider.

The harness was repaired on the working branch in commit
`8c0a9fab96077a4306380b3eddbd5359debc77bf`. The subsequent run on that commit
completed six Ollama calls and reached all correction scenarios, but none
completed successfully:

| Scenario | Validation result |
| --- | --- |
| `dp-correction-recipient-25` | `intent_analysis_validation`: `steps[].target_mentions[]` not grounded in step excerpt |
| `dp-correction-relation-endpoint-26` | `pending_corrections_validation`: invalid pending-correction payload |
| `dp-correction-two-rounds-27` | `intent_analysis_validation`: `steps[].target_mentions[]` not grounded in step excerpt |
| `dp-correction-ungrounded-28` (3 repetitions) | `intent_analysis_validation`: target mention not grounded in player evidence |

Some responses also supplied a non-action category with a non-null active-step
pointer; the provider-boundary normalization cleared that pointer, after which
strict validation still rejected the response. The normalization is
fail-closed, but the model is not respecting the correction response contract.

## Root-cause analysis

### 1. Reference resolution is coupled to world-write eligibility

Two guards currently conflate separate responsibilities:

1. `ConversationReferenceResolver.resolve()` immediately returns an empty
   result when `analysis.allows_world_proposal` is false.
2. `TurnResolutionService` builds the bounded context projection and invokes
   conversation resolution only when a world proposal is allowed or mechanics
   context is needed.

This creates a circular dependency for NPC reports and NPC speech. Intent is
required to leave a history-resolved pronoun literal (for example, `ella`)
rather than invent a canonical name. But a report/dialogue step whose actor is
an NPC and whose current utterance contains no literal speaker name may not
satisfy `allows_world_proposal`. The resolver is then skipped, so the system
cannot use the history/context to identify or clarify the referent.

Reference resolution is an interpretation aid; it is not permission to write
to the world. A resolved reference must never change the existing downstream
world-proposal gate. The resolver should be allowed to produce an audited
reference or clarification for questions, dialogue, reports and eligible
planned steps, while mechanics and persistent proposals continue to require
their existing authorization checks.

This guard is a concrete code-level explanation for at least part of the
observed entity-link collapse. It does not prove that every missing link is
caused by this guard: the live evaluator currently does not expose enough
per-case detail to distinguish a missing model mention from a skipped resolver.
The new tests/metrics must report both stages separately.

### 2. Pending correction asks the model to reconstruct too much

The current pending-correction request asks the provider to return:

- a complete replacement `PlayerIntentAnalysis`;
- all original steps, targets, action-frame arguments and relations;
- the correction proposal(s);
- evidence excerpts that satisfy the normal full-analysis validator.

At the same time, the correction prompt says the latest player answer is the
only evidence for the revised interpretation and that the prior analysis is
not authoritative. The prior step's predicate and unchanged mentions usually
belong to the original utterance, not to the latest answer. A full re-analysis
therefore has to preserve old literal fields while pretending they were all
written in the latest answer. Strict step-local evidence validation then
rejects the response.

This is a contract conflict, not something that should be fixed by weakening
the validator. The model should propose only a bounded typed edit. The
application already has `PendingIntentCorrection.apply()`, which validates
the latest answer, checks that the old value matches the pending state, updates
only the targeted slot, and preserves all other fields deterministically.
Requiring the LLM to regenerate the entire analysis duplicates that work and
introduces unnecessary failure modes.

The replacement contract should therefore return only:
- a status (`corrected`, `needs_clarification` or `no_change`);
- zero to four typed `pending_corrections`;
- a clarification question only when the status requires clarification.

The backend applies accepted corrections to the stored pending analysis. The
model must not rewrite category, actor, modality, polarity, outcome, predicate,
relation family/direction, evidence provenance or any unrelated slot.

### 3. One correction fixture has an invalid pending-state precondition

`dp-correction-ungrounded-28` starts from:
`Entrego la carta a Mara o a Aldric, todavía no lo he decidido.`

The old helper selected one recipient by a fixed preference order and
constructed a normal positive active action. That turns an explicitly
undecided recipient into a falsely resolved pending value. The synthetic
pending analysis must instead represent the two alternatives as unresolved
and already require clarification. The answer `No, me refería al otro.`
must not be accepted as a unique replacement; the model should ask which
person the player means.

### 4. Some speech-act fixture wording is not discriminative enough

Phrases such as `Ella responde a mi pregunta` and
`Ellas responden desde el balcón` can describe verbal answers, but can also
describe non-verbal responses in context. They are weak gold examples for a
hard dialogue-versus-report boundary.

The fixture should use unmistakable speech evidence when it expects
`dialogue` (for example, an explicit saying/asking verb or a clearly verbal
answer), while retaining separate ambiguous examples whose correct result is
abstention/clarification. Benchmark labels must not silently force one
interpretation of genuinely ambiguous language.

## Implementation strategy

This PR focuses on two separable boundaries:

1. **Reference resolution independent of proposal authorization.**
   Resolve eligible literal mentions using the visibility-filtered bounded
   context even when a turn cannot propose persistent changes. Add explicit
   regression tests for question/dialogue/report/planned categories. Keep
   `allows_world_proposal`, mechanics eligibility, visibility and write
   authorization unchanged.
2. **Correction-only provider contract.**
   Ask the model for typed pending edits and a correction status only. Apply
   those edits to the existing pending analysis with
   `PendingIntentCorrection.apply()`. Never ask the model to regenerate
   unchanged semantic fields. Keep the latest-answer evidence check strict.
3. **Benchmark repair and diagnostics.**
   Bring the `relation_endpoint` helper repair into main, construct the
   ambiguous precondition honestly, and make dialogue gold examples
   unambiguous. Add per-case reporting that separates (a) mentions emitted by
   Intent, (b) resolver invocation/gating, (c) references returned, and
   (d) clarification/abstention reason. Do not log prompts or completions.

## Acceptance criteria

- Deterministic tests prove that reference resolution can return a safe
  reference or clarification for non-write-authorized categories.
- A resolved reference alone never makes `allows_world_proposal` true and
  never triggers mechanics or persistent writes.
- Pending-correction deterministic tests cover accepted recipient edits,
  relation endpoint edits, two-round edits, ambiguous/no-change answers,
  stale previous values, and committed-resolution rejection.
- The live correction holdout reaches all scenarios without any full-analysis
  evidence mismatch; accepted edits must match exact latest-answer literals.
- Re-run the same pinned 12B discourse holdout. Report Intent, reference
  resolution, correction outcomes, provider validation errors, abstentions,
  latency, and false persistent changes separately.
- Preserve the existing safety baseline: zero critical false persistent
  changes and zero secret leaks.
- Run all deterministic CI, lint and typing checks. Do not merge with any
  required check failed or pending.

## Explicit non-goals

- No vector database, embeddings or broader memory infrastructure: context
  retrieval already measured 100% in this run.
- No increase in model permissions, no canonical IDs generated by the model,
  no relaxed evidence validator, and no automatic acceptance of ungrounded
  corrections.
- No broad rewrite of all Intent categories or additional model agents in
  this PR. Dialogue/report/question classification and callback/ellipsis
  accuracy remain measured follow-up work after these stage contracts are
  trustworthy.


## PR #237 implementation status

The branch `fix/237-reference-and-correction-evidence` implements the
following changes against the merged PR #236 base:

### Reference understanding

- `ConversationReferenceResolver` no longer returns an empty result solely
  because `allows_world_proposal` is false.
- Its eligible modalities now include question, planned and conditional
  mentions as well as action/report/dialogue references.
- `TurnResolutionService` builds a bounded visible context projection when a
  non-write turn contains literal target mentions, action-frame arguments or
  relation claims, then runs conversation-reference resolution.
- Typed world-reference resolution is still invoked only for turns that pass
  `allows_world_proposal`.
- The existing mechanics and extractor gates remain intact. New deterministic
  tests cover NPC reports, NPC dialogue and DM questions that resolve pronouns
  while remaining non-write-authorized, plus a service-level question path
  that stops on clarification before mechanics or proposal.

### Pending corrections

- `INTENT_CORRECTION_RESPONSE_SCHEMA` is now a correction-only contract:
  `status`, `pending_corrections`, and `clarification_question`.
- The correction prompt explicitly prohibits regenerating `intent_analysis`.
- Accepted corrections are applied to the stored pending analysis with
  `PendingIntentCorrection.apply()`; all unchanged fields are preserved and
  checked against the provider result.
- `corrected` clears the clarification being resolved;
  `needs_clarification` retains the pending state and sets a new question;
  `no_change` leaves the pending state unchanged.
- Deterministic tests now cover accepted corrections, no-change and ambiguous
  responses without requesting a second full semantic analysis.

### Evaluation harness

- The post-merge `relation_endpoint` fixture/helper mismatch is included in
  this branch; the relation endpoint scenario now constructs the correct
  pending relation state.
- The ambiguous two-recipient fixture no longer seeds a fabricated single
  recipient. Its pending analysis retains both alternatives and requires
  clarification.
- Four gold utterances were made more discriminative without changing their
  intended categories: the two single-NPC replies now explicitly state that
  the answer is spoken, the plural reply is explicitly verbal, and the
  ambiguous-speaker uncertainty example explicitly asks the DM to identify
  the speaker.
- Live discourse telemetry now distinguishes whether Intent emitted mentions,
  whether the resolver ran, how many references it returned, whether it asked
  for clarification, and why it returned no reference. The previous
  `reason=resolved` label for an empty, non-clarifying result has been
  replaced by `no_reference_returned`.

### Validation status

These changes have been committed to the PR #237 branch, but the deterministic
CI run has not yet been observed for this branch and no new local Ollama run
has been completed against the changed contract. Do not treat the PR as
validated until CI is green and the same pinned local discourse and correction
evaluations have been repeated. The earlier 16 November metrics above remain
the baseline; they are not results from PR #237.
