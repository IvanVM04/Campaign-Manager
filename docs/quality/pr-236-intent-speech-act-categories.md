# PR #236 — Intent speech-act, actor and action-family guidance

## Triggering live evaluation

The full held-out Gemma 4 12B discourse evaluation was rerun after PRs #234
and #235 were merged, using the same local model and role configuration:

- Intent model: `gemma4:12b-it-q4_K_M`;
- Ollama endpoint: `http://localhost:11434`;
- general model setting: `gemma4:26b`;
- Intent thinking disabled;
- 24 non-correction scenarios, with critical scenarios repeated three times;
- 44 provider calls completed in approximately 289.29 seconds;
- pytest result: one live corpus test failed; three unrelated tests were deselected.

The provider completed its requests normally. The remaining failures were semantic,
not connection or timeout failures.

### Current semantic metrics

| Family or metric | Result |
| --- | ---: |
| Context retrieval — local grammatical agreement | 100% |
| Context retrieval — long-distance reference | 100% |
| Intent — ellipsis / pending action | 50% |
| Intent — explicit callback | 25% |
| Intent — local grammatical agreement | 0% |
| Intent — long-distance reference | 0% |
| Intent — NPC quoted-speech attribution | 30% |
| Intent — topic boundary | 50% |
| Resolution — local grammatical agreement | 25% |
| Resolution — long-distance reference | 30% |
| Semantic-slot precision | 68.75% |
| Semantic-slot recall | 57.89% |
| Semantic-slot F1 | 62.85% |
| Entity-link precision | 100% |
| Entity-link recall | 14.29% |
| Correct / incorrect abstentions | 15 / 0 |
| Critical false persistent changes | 0 |
| Secret leaks | 0 |

NPC speaker hints were retained in the rendered Intent prompt for all expected
speaker cases. Context retrieval was also complete for the evaluated reference
cases. These results isolate the remaining problem more clearly: retrieving
context is not the same as interpreting the player's speech act and extracting
the right literal references.

The run still showed validation failures, including an ungrounded relation
subject, relation predicate and target mention, plus an active step reporting
a resolved outcome. PR #235 reduced the prominence of the earlier surface-form
failures but did not eliminate strict validation errors. No decoder or
evidence validator was relaxed.

## Findings

1. **Speech act and grammatical form were conflated.** An indirect question
   directed to an in-world character is dialogue, not a question addressed to
   the DM. The presence of an interrogative complement does not determine the
   global category.
2. **The actor and the category were conflated.** A present-tense verb does
   not automatically describe an attempt by the player. A reported physical
   event performed by an NPC is a report with the NPC as actor.
3. **Speech predicates were sometimes assigned the generic interaction
   family.** Asking, telling and replying are communication acts. They should
   not be mapped to interaction merely because an interlocutor is involved.
4. **Two fixture labels were inconsistent with the existing category
   contract.** `dp-grammar-name-no-inference-18` (`Ella entra en la sala.`)
   and `dp-grammar-contradictory-local-19`
   (`Ella me entrega el documento.`) describe NPC physical events, not
   dialogue. Their expected category is now `report`. This is a benchmark
   correction, not a change to model scoring rules.

## Changes

- Define `action`, `dialogue`, `question`, `report` and `plan` in the
  normal Intent prompt using actor-aware rules.
- Explicitly distinguish an in-world indirect question addressed to a
  character from a request for information addressed to the DM/narrator.
- State that an NPC's non-speech event is not a player attempt; preserve the
  actual NPC actor and use observed/reported modality.
- Define `communication` for linguistic acts (asking, telling, speaking,
  whispering and replying) and reserve `interaction` for non-linguistic
  physical manipulation/contact.
- Apply the same category distinction during pending-correction
  re-interpretation.
- Add corresponding JSON Schema descriptions and offline contract tests for
  both the normal and correction prompts.
- Correct the two NPC physical-event expectations and add a deterministic
  fixture test that distinguishes those reports from NPC speech acts.

The prompt uses newly authored examples rather than copying the held-out
scenario inputs. It does not contain answers to the evaluation cases.

## Safety and compatibility

This PR does not change the domain enums, relax strict decoding, rewrite model
completions, resolve pronouns, add canonical IDs or grant world-write
authorization. Actor, modality, evidence, reference resolution and persistence
remain separate validated fields and responsibilities.

## Validation

Run:

```powershell
python -m pytest tests/test_intent_speech_act_contract.py tests/test_discourse_pipeline_holdout.py -q
python -m pytest tests/test_modular_language_pipeline.py tests/test_player_intent_analysis.py tests/test_semantic_frames.py -q
```

After merge, repeat the full held-out evaluation with the same pinned model and
compare category accuracy, action-frame family/roles, entity-link recall,
validation failures by field, abstentions and persistent-change safety. A
prompt-contract test is not evidence that the local model follows the policy.

The unresolved live errors remain acceptance blockers for reliable language
understanding. In particular, zero Intent accuracy in the grammatical-agreement
and long-distance-reference families must not be hidden by perfect context
retrieval or zero critical false writes.
