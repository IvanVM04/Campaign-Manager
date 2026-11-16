# PR #246 — Discourse continuity, actor attribution and evidence boundaries

## Mission

Improve the existing Intent/discourse pipeline across three connected failure areas without adding a new semantic subsystem or weakening the evidence validator:

1. Recover explicit callbacks and elliptical actions from the correct prior topic.
2. Classify the fictional actor and speech act consistently, especially NPC speech versus NPC physical reports.
3. Keep historical names, NPC quote labels and prior action wording out of current player-evidence fields.

## Baseline

The local held-out Gemma 4 12B run on 16 November 2026 reported:

- Context recall: 100%.
- Entity-link precision and recall: 100%.
- Semantic-slot precision, recall and F1: 94.74%.
- Correct abstentions: 15; incorrect abstentions: 0.
- Critical false persistent changes: 0; secret leaks: 0.
- Intent accuracy by family: ellipsis/pending action 25%, explicit callback 0%, local grammatical agreement 50%, long-distance reference 100%, NPC quoted-speech attribution 90%, topic boundary 25%.
- Repeated failures included third-person NPC speech classified as report, a third-person NPC physical event classified as player action, and one historical ambiguous NPC alias emitted as a current action-frame argument and rejected by evidence validation.

The baseline points to a post-retrieval interpretation problem. This PR therefore does not add embeddings or expand world retrieval.

## Implementation

### Callback scoping

- Extract content anchors after explicit callback markers.
- When an older topic segment is reopened, select the best-matching earlier segment instead of feeding unrelated newer segments to Intent.
- Preserve ties between equally matching prior segments so downstream resolution can abstain.
- Preserve bounded history when a callback has no lexical anchor or no matching turn; the prompt explicitly tells the model not to guess.
- Pass selected history consistently to context retrieval, rendered history and the discourse index.

### Ellipsis and action continuity

- Render the latest player-authored same-topic turn as a historical candidate for a current ellipsis.
- Distinguish a repeated action (a new attempt) from a continuation that still needs evidence that the prior action is unfinished.
- Allow recovery of semantic meaning for the action description only. Historical verbs, names, arguments and excerpts remain ineligible for current literal evidence fields.

### NPC actor and speech-act interpretation

- Expand current-message speech-predicate recognition to common Spanish present, past and plural forms.
- Emit a hint when explicit local grammatical apposition in player-authored history uniquely identifies a visible NPC that agrees with a current third-person subject pronoun.
- Preserve plural agreement as a possible group, never a single entity.
- Emit an explicit ambiguity warning when a historical speaker alias is shared by multiple visible NPCs.
- Strengthen Intent and JSON Schema descriptions: actor is the fictional/grammatical actor, not the message sender; NPC speech is dialogue, NPC non-speech events are reports.

### Evidence boundaries

- Reiterate that discourse hints, quote labels and history are context only, not current player evidence.
- Historical canonical names must not replace current pronouns in target mentions, action arguments, relation endpoints, attribution or evidence excerpts.
- No changes are made to strict evidence decoding or world-write/mechanics authorization gates.

## Tests

Deterministic coverage adds:
- Anchor-based callback segment selection and no-anchor abstention.
- Ellipsis history hints with an explicit context/evidence boundary.
- Unique singular NPC pronoun agreement and unresolved third-person subjects.
- Plural NPC group preservation.
- Ambiguous NPC speaker alias warnings.
- Current unquoted speech-predicate cues and quote separation.
- Prompt contract for continuity, actor roles and evidence boundaries.
- Updated callback holdout expectations to match scoped history behavior.

## Validation commands

Run:

```powershell
python -m pytest tests/test_discourse_context_builder.py tests/test_discourse_pipeline_holdout.py tests/test_intent_speech_act_contract.py -q
python -m pytest tests/test_conversation_reference_resolver.py tests/test_modular_language_pipeline.py -q
ruff check .
pyright models rules_engine bootstrap operations
python -m pytest -m "not real_llm" --cov --cov-report=term-missing --cov-report=xml
```

Then rerun the pinned local Ollama holdout:

```powershell
python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -k "held_out_discourse_intent_and_resolution_corpus" -v -s --junitxml=.pr246-discourse-after.xml 2>&1 | Tee-Object -FilePath .\pr246-discourse-after.log
```

The live holdout is a required acceptance step. Deterministic CI cannot establish that Gemma follows the improved discourse hints. Compare the same model digest and server version when possible.

## Safety invariants and non-goals

- No name or ID is inferred by the model or introduced into current evidence.
- No ambiguous alias is attributed to one NPC.
- No ungrounded mention is silently accepted or canonicalized.
- No change to domain enums, mechanics authorization, persistent-write gates, correction contracts or reference visibility rules.
- No new memory store, embeddings, model agent or provider call in the normal Intent path.
- The expected benefit is more focused history and clearer instructions, not a claim that an LLM becomes deterministic.
