# Intent surface semantics hardening — 2026-11-18

## Motivation and measured baseline

This change follows the local Ollama evaluation on main commit
`4a64fff494336665779f2f412f6ad8f5b1a465b1`, using
`gemma4:12b-it-q4_K_M` (digest
`6114515d63c17436a7c0417d82820ac65ad643e2806c5a3c89cb62846436ed0b`),
Ollama `0.40.16`, `think=false`, and a 300-second timeout.

The language-understanding holdout ran 26 scenarios / 46 provider calls in
798.931 seconds. It failed with two critical mismatches and seven
observational mismatches. Provider requests did not fail in transport.
Negation/failure, epistemic uncertainty, question and quoted-speech families
had 1.0 case accuracy. Weak families included compound action (0.6),
plan/conditional (0.6), observation/report (0.8), and action attempts (0.5).

The semantic-frame holdout passed (20 scenarios / 36 provider calls,
semantic-slot F1 0.9863, precision 0.973, recall 1.0). Its remaining
observational mismatch was the location argument in a hiding construction:
the location mention omitted its spatial preposition. The integrated
failed-compound-action probe passed in 36.05 seconds and produced no proposal
operations for that failed action.

## Findings translated into code-level fixes

1. **Unreported attempt outcomes.** A positive player attempt is not an
   uncertain result merely because the model selected `uncertain`. The
   normalizer now resets unsupported outcome claims to `not_claimed`, while
   preserving explicit epistemic uncertainty and literal success/failure
   evidence. It does not relax the typed validator.
2. **Future plans.** First-person future forms become `planned` unless an
   explicit `si` conditional construction makes them `conditional`.
   Negative and epistemically uncertain futures are excluded.
3. **Single-step observations.** Explicit first-person perception predicates
   become player-authored `observed` reports with no active action pointer.
4. **Compound sequences.** A completed first-person present action followed
   by a separately expressed attempt is normalized to a resolved first step
   and one active second step. Both literal excerpts must appear in order,
   with an explicit sequence linker between them. The existing observation +
   attempt rule now requires the same ordered-evidence check and resolves
   the first-step polarity required by the active-step invariant.
5. **Object corrections.** For an explicit correction, an ungrounded action
   predicate is replaced only with the literal predicate from the correction
   construction (for example, `era`). The entire short utterance becomes the
   step excerpt before strict domain decoding.
6. **Spatial role mentions.** Hiding-location templates now retain the
   preposition in the location mention (`bajo la alfombra...`) and tests
   cover all five supported prepositions.
7. **Additional language edge cases.** Refusals such as «No quiero intentar»
   remain negated and non-actionable. Explicit «no consigo» failures resolve
   the attempt even when the sentence does not use «pero». Sequence linkers
   may be located between excerpts or at the start of the later excerpt,
   while literal ordering checks remain mandatory.
8. **Prompt/schema alignment.** Intent prompt and schema now define
   unreported outcomes, player observations, first-person future plans and
   completed-action-then-attempt sequences. `mixed` includes materially
   different modalities across ordered steps, even when both are player
   actions; this matches the existing compound-step evaluation contract.
9. **Targeted live diagnostics.** The language-understanding holdout accepts
   `CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID`, matching the semantic-frame
   holdout. A selected scenario is treated as a gate even if it is normally
   observational, and the selected ID is recorded in JUnit properties.

## Safety boundaries

- Held-out input fixtures and gold annotations are unchanged.
- Literal evidence checks remain strict.
- No canonical entity identity, IDs, permissions or world consequences are
  inferred by these normalizers.
- No model/provider calls are added.
- Explicit epistemic language is not collapsed into `not_claimed`.
- The outcome repair does not invent an active-step pointer or grant
  mechanical authorization when the model left that pointer unset.
- Explicitly refused attempts are not reclassified as positive attempts.
- A completed first action is inferred only when a first-person present-tense
  predicate, two ordered literal excerpts and an explicit sequence linker
  support the interpretation.
- Relation claims are not re-indexed by compound-step rules; such cases are
  left model-led.

## Deterministic validation

Run the focused offline checks first:

```powershell
python -m pytest tests/test_intent_surface_normalization.py tests/test_semantic_surface_hints.py -q
python -m pytest tests/test_mechanics_adjudicator.py tests/test_modular_language_pipeline.py tests/test_player_intent_analysis.py tests/test_semantic_frames.py -q
python -m pytest tests/test_predicate_evaluation.py -q
ruff check services/turns/intent_surface_normalization.py services/turns/semantic_surface_hints.py services/turns/intent_interpreter.py services/turns/intent_response_schema.py tests/test_intent_surface_normalization.py tests/test_semantic_surface_hints.py tests/test_real_llm_semantic_holdout.py
pyright models services/turns tests
```

## Live acceptance

Use the same model digest and Ollama version as the measured baseline.

First isolate the affected scenarios:

```powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID = "holdout-attempt-pickpocket"
python -m pytest tests/test_real_llm_semantic_holdout.py -m real_llm -k "held_out_language_understanding_corpus_v1" -v -s
$env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID = "holdout-correction-object"
python -m pytest tests/test_real_llm_semantic_holdout.py -m real_llm -k "held_out_language_understanding_corpus_v1" -v -s
$env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID = "holdout-plan-after"
python -m pytest tests/test_real_llm_semantic_holdout.py -m real_llm -k "held_out_language_understanding_corpus_v1" -v -s
$env:CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID = "holdout-compound-success-act"
python -m pytest tests/test_real_llm_semantic_holdout.py -m real_llm -k "held_out_language_understanding_corpus_v1" -v -s
Remove-Item Env:\CAMPAIGN_MANAGER_REAL_LLM_SCENARIO_ID
```

Then run the complete language, semantic-frame and integrated probes:

```powershell
python -m pytest tests/test_real_llm_semantic_holdout.py -m real_llm -k "held_out_language_understanding_corpus_v1" -v -s --junitxml="artifacts\post-intent-surface-language.xml"
$env:CAMPAIGN_MANAGER_REAL_LLM_REPORT_PATH = ".\artifacts\post-intent-surface-frames.json"
python -m pytest tests/test_real_llm_semantic_holdout.py -m real_llm -k "held_out_semantic_frame_corpus_v1" -v -s --junitxml="artifacts\post-intent-surface-frames.xml"
python -m pytest tests/test_real_llm.py -m real_llm -k "integrated_pipeline_does_not_advance_failed_compound_action" -v -s --junitxml="artifacts\post-intent-surface-integrated.xml"
```

Acceptance target: zero critical language mismatches, no observational
mismatches in targeted families, no regression from the semantic-frame F1
baseline, and continued absence of operations after a failed active step.
These are targets, not claims that the local model has already passed.
CI/offline tests cannot replace the pinned Ollama run or a later SillyTavern
smoke test.
