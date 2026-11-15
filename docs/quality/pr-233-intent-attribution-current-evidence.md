# PR #233 — current-evidence grounding for Intent step attribution

## Triggering live observation

After PR #232 was merged, the focused live Ollama scenario
`dp-topic-current-shift-01` was run with `gemma4:12b-it-q4_K_M`.

- Player input: `Cambiando de tema, ¿qué ocurre en la biblioteca?`
- Recent player turn: `Hablo con Mara sobre el contrato.`
- Ollama request completed; the focused case took 9.072 seconds.
- Intent decoding then failed with
  `evidence_not_in_player_text (field=steps[].attributed_to)`.

The current utterance contains no explicit speaker attribution. The prior
conversation contains a name, but the current-evidence contract does not allow
a history-only name to be copied into `IntentStep.attributed_to`. The failure
therefore identifies a grounding error at the provider boundary, not an Ollama
transport or timeout failure.

## Contract

`IntentStep.attributed_to` is an optional literal attribution from the
current player's evidence. For schema v2 it must also occur in that step's
`source_excerpt`.

Conversation history, discourse hints and world context may help interpret a
reference, but must not be copied into this field as if the player had written
the resolved name. If the speaker can only be inferred from historical context
or by resolving a pronoun, the safe value is `null`.

## Provider-boundary handling

The provider boundary now applies a narrow, conservative normalization before
the strict domain decoder:

- A non-empty string attribution that is absent from current player evidence
  is changed to `null`.
- For schema v2, an attribution absent from the step's own `source_excerpt`
  is also changed to `null`.
- Only the `attributed_to` field is changed. Step order, source excerpt,
  actor, action, category, modality, polarity, outcome, action frame and
  relation data remain untouched.
- Malformed step structures, non-string attribution values and other invalid
  evidence fields are not repaired; they remain on the strict validation path.
- A safe warning records only the affected step indexes and normalization name.
  It does not log model-supplied attribution text, player evidence or prompt
  content.

This is removal of unsupported authority, not a positive inference. In
particular, a non-player observed/reported step whose attribution is cleared
cannot satisfy the existing world-proposal requirement for a grounded
`attributed_to`.

`PlayerIntentAnalysis.from_payload()` remains strict. Direct domain decoding
continues to reject an unsupported attribution with
`evidence_not_in_player_text`.

## Regression coverage

Deterministic tests cover:

1. A topic-shift question with a historical NPC name: the unsupported
   attribution is cleared, while the question category and null active step
   are preserved.
2. A reported statement that explicitly names the NPC in the current utterance:
   the literal attribution is preserved.
3. Direct domain decoding of the history-only attribution: strict rejection
   remains unchanged.

Run the focused deterministic tests with:

```powershell
python -m pytest tests/test_modular_language_pipeline.py -k "attribution or step_indices or non_action_active_step" -q
python -m pytest tests/test_intent_validation_diagnostics.py tests/test_player_intent_analysis.py -q
```

## Live acceptance

After the PR is merged, rerun the single held-out scenario with the pinned
Gemma 4 12B model. The intended result is that Intent validation proceeds past
`steps[].attributed_to`, classifies the utterance as a question and keeps
`active_step_index=None`. This single case is a regression probe, not proof
of corpus-wide semantic accuracy.
