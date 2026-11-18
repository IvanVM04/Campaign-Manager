# Intent reports, epistemic scope and explicit abstention hardening

Date: 2026-11-18

## Motivation

The post-PR-265 Ollama evaluation exposed two intent-understanding gaps:

- A reported proposition could be split into multiple intent steps. The existing surface normalizer only attributed a reporting speaker and applied epistemic uncertainty when there was exactly one step.
- A first-person decision such as deciding not to perform an infinitive was not covered unless the wording explicitly contained a form of “intentar”. A model-generated follow-up step describing the player as remaining outside could consequently be mistaken for another attempted action.

These are semantic interpretation issues, not provider transport failures. The changes in this patch keep the deterministic layer bounded to constructions that are explicit in the current player-authored evidence.

## Reported propositions and uncertainty

When a literal reporting construction appears at the beginning of the player utterance (for example, a named or indefinite source afirma que / asegura que something), normalization now:

1. Finds steps whose literal excerpts fall inside that reported clause.
2. Attributes those steps to the literal source and assigns the reported modality.
3. Applies an epistemic caveat to the reported proposition when an uncertainty marker occurs before the end of the same sentence, even if the model put the caveat in a separate step.
4. Leaves steps from later sentences outside that attribution and uncertainty scope.
5. Widens the evidence excerpt only when the complete utterance fits the schema's existing excerpt limit. Longer utterances do not bypass attribution evidence validation.

The rule does not infer a canonical NPC identity, confirm the reported proposition, or let a report become an active player action. Uncertainty remains distinct from positive world evidence.

## Explicit decisions not to act

A first-person explicit decision followed by no and an infinitive is normalized as a negative, resolved player step. It does not require the verb intentar.

A directly linked, literal abstention-state continuation (such as remaining or staying outside) may be folded into the decision's evidence step when it is the only other model-generated step. This avoids representing the confirming state as a second attempt.

A genuinely distinct later positive attempt is preserved in order and can remain the active step. The normalizer does not cancel a later action merely because an earlier decision was negative.

Negative steps remain non-actionable: they cannot become active attempts or independently authorize world proposals. An epistemically uncertain reported step is also resolved as a speech act for sequence ordering, so it does not block a distinct later positive player attempt; the uncertain report itself remains ineligible to authorize a proposal.

## Broader polarity, failure and speech-scope coverage

The hardening now distinguishes three cases that must not collapse into one signal:

- An explicit first-person refusal or abandoned intention (for example, preferring not to act, refusing, abstaining, cancelling an attempt, or abandoning an action idea) is a resolved negative intent.
- A direct inability/result statement such as not managing to open something is a resolved failure when it explicitly describes the attempted action. It is not the same as choosing not to try.
- Uncertainty is attached to an attempt outcome only when the wording explicitly refers to that outcome (for example, not knowing whether the attempt succeeded). A doubt about a guard or another unrelated fact does not deactivate the player's attempt.

The refusal rule is excluded from player dialogue and reported-source constructions. A negative proposition inside quoted speech or a reported claim retains that speaker/modality and does not become a player refusal. Reported uncertainty is scoped to its proposition; a distinct player action can follow it in the same sentence or a later sentence. The attribution evidence span ends with the reported clause rather than absorbing a later action.

The held-out language corpus now contains 34 scenarios. New cases cover preference/refusal, negative dialogue, direct failure, uncertain reports followed by live actions, uncertainty about an attempt's own result, unrelated uncertainty after an attempt, an NPC report followed by a player action in the same sentence, and a refusal followed by a distinct attempt. All eight new cases are critical three-repetition gates; they remain holdout-only and are not copied into the prompt.

## Evidence and safety invariants

- source_excerpt must remain literal player-authored evidence.
- The normalizer does not loosen PlayerIntentAnalysis validation.
- No action predicate, entity ID, permission, action outcome or world consequence is invented.
- Attribution is applied only when the reporting speaker and predicate are literal in the current utterance.
- Epistemic scope stops at a sentence boundary; it does not contaminate a later player action.
- The negative decision rule is constrained to first-person decision forms and a literal infinitive.
- Abstention continuation collapse requires each remaining step to be wholly contained in the matched continuation phrase and is disabled when relation claims are present.

## Regression and live-evaluation gates

The deterministic tests cover:

- multi-step reported claims with same-sentence uncertainty, including an independent player action in the same sentence;
- non-propagation into a later independent player action;
- negative decisions with an abstention-state continuation and varied refusal forms;
- preservation of a genuinely distinct later positive attempt, including after a reported uncertain clause;
- interpreter-level assertions that uncertain reports and negative decisions are not actionable and do not authorize a world proposal.

The original critical rumour, compound-observation and refusal scenarios remain gates. The new critical gates separately exercise the distinctions above over three repetitions. No held-out expected semantic fields are changed to make the tests pass.

Local Ollama verification should use the same pinned model digest and provider settings as the baseline, and should include both the full language-understanding holdout and the integrated failed-compound-action test. Passing deterministic CI does not substitute for this real-provider verification.
