# Player-message comprehension phase — 2026-11-18

## Purpose

This phase closes several concrete gaps around discourse continuity and multi-step player messages without replacing the shared Intent interpreter, changing the durable turn pipeline or weakening the evidence boundary.

The implementation is deliberately deterministic where the evidence is explicit and conservative where identity remains ambiguous. It does not add model calls, embeddings, a persistent conversation-memory layer or new world-write authority.

## Changes

### 1. Dative clitics become independent surface mentions

The resolver already discovers third-person subject pronouns independently of the model's emitted targets and frame arguments. It now also detects a narrow, curated set of dative clitics (le / les) when immediately followed by a supported finite speech/interaction verb form. If the same clause explicitly names the recipient with an a/al complement that matches another literal mention or a visible entity (or is a capitalized proper name), the clitic is coalesced with that explicit reference instead of generating a second resolution. Adverbials such as «a menudo» and «a veces» do not suppress the clitic.

- The original span and casing are preserved.
- The clitic is not replaced with a canonical NPC name in player evidence.
- le records singular number with unknown gender.
- les records plural number with unknown gender.
- Articles and unrelated uses are not treated as references; detection requires a supported following verb.
- The resolver can use the clitic even when the model omitted it from optional mention/argument arrays.

Plural resolution remains stricter than a score winner: les only forms a group from at least two visible candidates co-mentioned in the same historical evidence excerpt, with explicit local singular agreement for each member and a unique most-recent co-mention. This permits a mixed-gender group while preserving abstention when membership is not proved.

### 2. Named NPC speech signals

The typed speech-signal extractor now handles both pronoun subjects and named subjects when the exact label/alias belongs to exactly one active visible NPC. The Intent prompt also spells out independent per-step actor/modality/polarity assignment, event-order preservation, category selection for multi-step messages, and the resolved-negative-step rule.

It ignores quoted spans, inactive entities and aliases shared by multiple visible NPCs. Named signals are prompt hints only; they carry no canonical ID, do not rewrite the Intent result and do not authorize a world proposal. The player-authored excerpt remains the only source for literal evidence.

### 3. Callback anchors stop at the introductory clause

Callback anchor extraction now prefers the clause immediately following the reactivation marker and before the first comma, semicolon or sentence boundary. This prevents the later action/question from polluting the retrieval anchor.

When that introductory clause contains no meaningful anchor, the existing bounded suffix fallback remains. Selection exposes the scored historical segments in DiscourseSelection.candidate_scores for deterministic diagnostics; ambiguous ties remain ambiguous.

### 4. Explicitly negated steps can precede a later active attempt

A prior NEGATED step is considered resolved only when its polarity is explicitly NEGATIVE. It can therefore precede a later positive active attempt in a compound message. A negated step with positive/uncertain polarity, and any unresolved earlier attempt, still blocks the active-step pointer.

This changes no write authorization for the negated step: allows_world_proposal continues to exclude negated modalities.

### 5. Held-out compound-intent evaluation

Two new fixtures add 14 Spanish-first, multi-step messages and an independent per-step gold sidecar.

The corpus covers sequential player actions, player/NPC dialogue exchanges, multi-NPC events, three-step actor changes, conditional plans and an explicit negative-then-positive sequence. The negative-then-positive case is globally categorized as action because both steps are actions; multiple steps alone do not imply mixed. Every case has two or three expected steps. The utterances are new relative to the existing language, semantic-frame, conversation and discourse holdouts.

The gold sidecar stores only scenario IDs and per-step actor, modality and polarity; it contains no player text, entity IDs or prompt examples. Deterministic tests protect corpus integrity and verify that the utterances are not embedded in the Intent system prompt.

The evaluator scores independently:

- global category;
- active-step index;
- step count;
- actor for every step;
- modality for every step;
- polarity for every step.

Missing steps count as false negatives; extra steps count as false positives. A correct first actor cannot hide errors in later steps. The live evaluator is opt-in and uses the pinned local Ollama environment. Its optional JSON report stores aggregate metrics and numeric provider-usage totals only.

## Validation commands

Deterministic contracts:

```powershell
python -m pytest tests/test_discourse_context_builder.py tests/test_discourse_pipeline_holdout.py tests/test_player_intent_analysis.py tests/test_compound_intent_evaluation.py -q
```

Focused live Ollama holdout:

```powershell
$env:CAMPAIGN_MANAGER_GIT_COMMIT = (git rev-parse HEAD).Trim()
$env:CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_REPORT_PATH = ".\artifacts\compound-intent-v1.json"
python -m pytest tests/test_real_llm_compound_intent.py -m real_llm -v -s --junitxml=.compound-intent-v1.xml 2>&1 | Tee-Object -FilePath .\compound-intent-v1.log
```

A single scenario can be isolated with CAMPAIGN_MANAGER_REAL_LLM_COMPOUND_SCENARIO_ID. The live test repeats critical scenarios three times in the complete run; a focused scenario runs once for diagnosis.

## Safety invariants

- No prompt, completion, player utterance, narrative, campaign state, evidence excerpt or raw provider event is written to the compound report.
- Canonical IDs remain backend-only.
- History is context, never new player-authored evidence.
- A named speech signal is restricted to a unique active visible NPC and is only a hint.
- A plural clitic does not select the highest-scoring individual; it requires a uniquely evidenced co-mentioned group.
- Negated actions do not become active attempts or world proposals.
- No mechanics, operation validation, visibility, durable commit or SillyTavern lifecycle authority is changed.

## Acceptance boundary and remaining work

This PR adds deterministic coverage and an opt-in live probe; it does not claim that the current local model passes the new corpus. The 14-case gold is a focused engineering benchmark, not a general Spanish discourse benchmark. Clitic recognition is intentionally lexicon-bounded, named-NPC speech recognition is limited to direct subject–verb adjacency, and implicit topic shifts remain outside this increment.

The next acceptance step is to run the new compound holdout and the existing discourse/predicate holdouts against the same recorded model digest, Ollama version and generation settings. Compare all per-step actor/modality/polarity metrics, entity precision/recall and abstentions. Manual SillyTavern acceptance remains separate: multi-chat isolation, callback/topic change, clarification, restart/retry and durable replay must be checked in the user's actual setup.
