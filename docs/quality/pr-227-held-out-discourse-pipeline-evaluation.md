# PR #227 — Held-out discourse and staged pipeline evaluation

**Status:** Draft PR #227; WP0–WP6 implementation and documentation are in place. Final CI on the latest head and user-run Ollama/SillyTavern acceptance remain open.  
**Branch:** `feat/227-held-out-discourse-pipeline-evaluation`  
**Base:** `main` at `61725a03346d2ebfcf0ce6b2aacf92c0b6789b28` (includes merged PR #226).  
**Dependency:** PR #226 is merged at `61725a03346d2ebfcf0ce6b2aacf92c0b6789b28`. This PR is independent of the former #226 feature branch.  
**Priority:** P1 immediately after the modular pipeline hardening; measurement before further semantic feature expansion.  
**Owner of next action:** resume from the durable checkpoint in §9. Do not create another branch or PR.

## 1. Objective

Establish a reproducible, model-backed evaluation of the discourse capabilities added by PR #223 and the role-separated production pipeline completed by PR #226.

The repository already contains a **110-scenario evaluation foundation** (50 development and 60 held-out cases), a provider-agnostic metrics ledger, resolver holdouts, semantic-frame holdouts and live intent/frame tests. PR #227 must extend that foundation rather than recreate it.

The key gap is specific: PR #223 added twelve-turn history, topic segmentation/callbacks, ellipsis cues, local grammatical agreement and explicitly labelled NPC speaker attribution, but those additions do not yet have a dedicated live held-out evaluation tranche. PR #226 then established separate Intent, Mechanics and Consequence Planner responsibilities, but the new integrated architecture still needs stage-attributed quality results beyond its focused failed-compound-action probe.

**Primary question:** does the configured local model use the discourse evidence correctly, and does that understanding survive deterministic resolution and produce only justified mechanics/consequences?

## 2. Baseline inventory — preserve, do not duplicate

The current main branch already has:

| Existing corpus / test | Current coverage | PR #227 treatment |
|---|---|---|
| `language_understanding_corpus_holdout_v1.json` | 26 held-out utterance/intent cases | Preserve unchanged; reuse its scoring conventions. |
| `semantic_frame_corpus_holdout_v1.json` | 20 held-out action-frame/relation cases | Preserve unchanged; do not copy cases into the new tranche. |
| `conversation_understanding_corpus_holdout_v1.json` | 14 held-out deterministic reference cases | Preserve unchanged; it is primarily a resolver corpus, not a live discourse-pipeline benchmark. |
| `test_real_llm_semantic_holdout.py` | Live intent and semantic-frame evaluation plus a pending-recipient correction probe | Extend with a separate discourse/pipeline evaluator; retain old results as a comparable baseline. |
| `SemanticEvaluationLedger` | Per-family accuracy/slot recall/latency, semantic slot P/R/F1, entity-link P/R, abstention, context recall, operation P/R, critical false changes and secret leaks | Extend only where stage-level reporting cannot be represented cleanly; do not replace working metrics. |
| `test_modular_language_pipeline.py` | Deterministic shared-analysis hand-off, ambiguity/clarification, conditional mechanics, failed compound prerequisites and no-op routing | Preserve as deterministic contract coverage; add data-driven cases only for genuine uncovered gaps. |
| `test_discourse_context_builder.py` and resolver tests | Topic shifts/callbacks, twelve-turn scoping, ellipsis cues, NPC label parsing, local agreement and abstention | Preserve; add targeted regressions for gaps revealed by the new fixture, not duplicate assertions. |

The existing 110 scenarios remain a stable reference set. Do not renumber, rewrite, retune or move their held-out examples into prompts/few-shot instructions.

## 3. Scope and design decisions

### 3.1 New held-out discourse tranche

Add a separate fixture:

`tests/fixtures/discourse_pipeline_corpus_holdout_v1.json`

Target **28 new Spanish-first scenarios**, four in each family:

1. **Topic boundaries** — explicit shifts, ordinary subject continuity, incidental/quoted shift markers and no accidental leakage from a previous topic.
2. **Explicit callbacks** — return to an earlier topic within the twelve-turn window; callback retrieves the intended antecedent but never bypasses visibility, confidence or ambiguity checks.
3. **Ellipsis and pending action continuity** — uniquely recoverable omitted action, an antecedent that is already complete, interruption by a different topic, and a case requiring abstention.
4. **Long-distance reference and recency** — antecedent near the twelve-turn boundary, an antecedent outside the supported window, intervening distractors and multiple plausible candidates.
5. **Local grammatical agreement** — explicit local article/apposition cues, contradictory local cues, proper names without grammatical evidence, and plural references that must not resolve to one arbitrary person.
6. **NPC attribution and quoted/reported speech** — explicitly labelled visible NPC speaker, ambiguous speaker label, non-visible/unknown speaker, and names/instructions occurring inside someone else's quote.
7. **Multi-turn corrections** — latest-answer correction of an action argument, directed relation endpoint correction, two successive clarification rounds preserving the prior valid edit, and stale/ambiguous/ungrounded correction rejection.

Each scenario has a stable ID, family, criticality, current player input, bounded recent turns, visible world fixture and expected stage invariants. Expected outputs should be expressed as semantic constraints (roles, mentions, direction, modality, correct reference or abstention, route and allowed/forbidden consequence families), not brittle full-JSON snapshots.

For correction cases, keep the prior pending analysis, DM clarification and latest player evidence as separate fixture fields. The DM's question is context, never correction evidence.

### 3.2 Staged evaluation contract

The evaluation report must distinguish these stages:

- **Intent:** category, actionable step, actor, order, modality, polarity, reported outcome, action-frame roles, directed relation slots, attribution and literal-evidence grounding.
- **Discourse / resolution:** topic scope, callback behavior, antecedent link, correct abstention, speaker attribution and canonical identity after deterministic visibility/scope checks.
- **Context selection:** required visible facts retrieved, forbidden/secret facts excluded, and discourse/antecedent signals retained, compacted or omitted under the actual role-specific byte budgets.
- **Mechanics:** whether the stage was called when required, skipped when non-actionable/ambiguous, and whether its decision family is consistent with the validated active step. Dice/results remain deterministic.
- **Consequence planning:** operation-family precision/recall, duplicate/unsupported operations, order/conditional progression and final persistent changes. The planner consumes the shared analysis and trusted references; do not create a second intent interpretation.

The evaluation should call the real role-specific services. For a small curated subset, also exercise the real `TurnResolutionService` orchestration to verify the same analysis/reference/projection hand-off and final operation behavior. Do not make every corpus case invoke every model role: use explicit stage expectations so that questions, callbacks and corrections do not trigger irrelevant mechanics/planner calls.

### 3.3 Evaluation and safety rules

- Keep the existing 110-case corpora and their scores comparable.
- New examples stay in a distinct `split: held_out` fixture and must never be copied into prompts, schema examples or few-shot material.
- Integrity tests check unique IDs, normalized utterance uniqueness across all held-out corpora, family balance, required metadata and bounded history.
- Repeat critical cases three times; run non-critical cases once for the initial baseline.
- A provider/decoder exception is a failed case, never a skipped sample.
- Report metrics by stage **and** family. Do not hide weak stages in one aggregate score.
- Keep the current hard safety requirements: **zero critical false persistent changes** and **zero secret leaks**. Critical incorrect identity, false NPC attribution, invalid correction or failure to abstain on an ambiguous reference also fails.
- Do not set arbitrary non-critical accuracy targets before the first reproducible run with a pinned model digest/settings. Record baseline first, then propose evidence-based targets.
- Preserve all failed examples and mismatches even when a later repetition passes.
- No prompt text, raw completion, secret marker or private campaign content in logs. Record safe IDs, lengths, result families, counters, per-role models, token/timing metrics and run metadata only.

## 4. Proposed fixture contract

Top-level shape:

```json
{
  "schema_version": 1,
  "split": "held_out",
  "description": "Reserved for measurement; never use as prompt examples.",
  "scenarios": [
    {
      "id": "dp-topic-shift-01",
      "family": "topic_boundary",
      "critical": false,
      "input": "Current player utterance...",
      "recent_turns": [
        {"id": 1, "player_input": "...", "narrative": "..."}
      ],
      "visible_entities": [
        {"id": 11, "name": "Mara", "entity_type": "npc", "description": "..."}
      ],
      "expected": {
        "intent": {"category": "action", "active_step_index": 0},
        "reference": {"mention": "ella", "entity_id": 11, "clarification": false},
        "mechanics": {"call": true},
        "proposal": {"allowed_operation_families": [], "forbidden_operation_families": []},
        "context": {"required_entity_ids": [11], "forbidden_markers": []}
      }
    }
  ]
}
```

This is a contract example, not a literal required payload for every case. Keep optional stage expectations absent when a stage is not relevant. Add a documented fixture schema/validator so missing required expectations fail early. Multi-round correction cases may add a bounded `correction_rounds` array with prior analysis seed, DM question and latest player evidence per round.

## 5. Work packages

### WP0 — Branch, specification and resumability
- [x] Confirm PR #226 merged and use current `main` as the base.
- [x] Create `feat/227-held-out-discourse-pipeline-evaluation` from main.
- [x] Add this implementation specification and durable checkpoint.
- [x] Open [Draft PR #227](https://github.com/IvanVM04/Campaign-Manager/pull/227) and record its number/URL here.
- [x] Link this work from the active evaluation guide, corpus index, roadmap and documentation hub.

### WP1 — Corpus gap analysis and fixture design
- [x] Map the seven fixture families to the uncovered live-evaluation gap from PR #223 and stage-level contracts after PR #226.
- [x] Add normalized-input and cross-corpus ID de-duplication checks against all existing held-out fixtures.
- [x] Add the 28-case Spanish-first fixture with 7 balanced families (4 each).
- [x] Mark critical identity, visibility, ambiguity, agreement, NPC attribution and ungrounded-correction controls.
- [x] Add deterministic schema/count/family/ID/normalized-utterance integrity checks. The fixture remains separate from prompt examples.

### WP2 — Deterministic evaluation harness
- [x] Drive the real discourse builder and conversation resolver over fixture histories and visible entity worlds.
- [x] Score entity-link precision/recall, case outcomes and correct/incorrect abstentions with the shared evaluation ledger.
- [x] Cover callback/topic scoping, quote-safe markers, twelve-turn boundary, plural abstention, local grammar, NPC attribution and correction-evidence separation deterministically.
- [x] Keep all fixture, builder and resolver tests deterministic and offline.

### WP3 — Live intent and discourse evaluation
- [x] Add opt-in live Intent evaluation using all 24 non-correction scenarios and their bounded same-chat history.
- [x] Score intent category plus action-frame family/argument slots with multiset precision/recall/F1 for labelled frame cases.
- [x] Record prompt history/discourse bytes and retained/omitted discourse-index counts by family, separately from intent and resolver scores.
- [x] Repeat critical live intent/reference cases three times; preserve each mismatch and provider/decoder failure in test output/properties.
- [x] Record the resolved intent model/digest, Ollama version, timeout, calls, prompt bytes, token counts and timing where the server supplies them. Hardware/generation settings still need to be recorded in the user's local baseline report.

### WP4 — Context and mechanics stage evaluation
- [x] Add a deterministic Mechanics prompt regression proving only active-step canonical references enter the adjudication reference block; retain existing context recall/secret-exclusion tests.
- [x] Capture prompt-section byte sizes and discourse-index retained/omitted status per live intent scenario without logging section contents.
- [x] Reuse the #226 deterministic route matrix and add a live integrated attempted-action callback probe that requires a mechanics result.
- [x] The integrated live probe asserts a valid mechanics decision and deterministic natural-1 failure; dice/result authority is unchanged.

### WP5 — Consequence planner and integrated pipeline subset
- [x] Add a live full-orchestrator callback scenario using the role-specific extraction provider through TurnResolutionService.
- [x] Record integrated operation false-positive metrics for a failed prerequisite and add a positive explicit-NPC-fact probe that expects exactly one `update_entity:1`, no duplicate create, 1.0 operation precision/recall, and no Mechanics call for a completed observation.
- [x] Add full-orchestrator live probes for both a failed compound action (Intent → Resolution → Mechanics → Planner, no operations) and a completed NPC observation (Intent → Resolution → Planner, exactly one justified update and Mechanics skipped). Both record role-specific model digests/calls and prompt/token/timing properties.
- [x] Assert failed compound prerequisites produce no world operations; preserve the deterministic no-op route matrix for non-actionable/quoted/negative inputs.
- [x] Keep the original PR #226 integrated failed-compound-action probe as a separate test.

### WP6 — Reporting, documentation and handoff
- [x] Emit shared-ledger per-family intent/resolution/slot metrics and machine-readable prompt, provider, correction and integrated-operation properties.
- [x] Update the prompt-evaluation guide, corpus index and AI-understanding roadmap with exact fixture/test names, new 138-case inventory and acceptance boundaries.
- [ ] Record the first pinned-model baseline; do not claim a pass until the user runs the configured local Ollama model.
- [x] Synchronize this checkpoint with completed WP status, exact commands, live-acceptance boundary and next action.

## 6. Acceptance criteria

PR #227 is ready for review only when:

1. The original 110 scenarios remain unchanged and all new held-out scenarios are distinct.
2. The new 28-case fixture has seven balanced families, stable IDs and deterministic integrity validation.
3. Every stage's relevant expected outputs are measured separately; a stage that is not expected to run is asserted not to run.
4. Resolver metrics include precision/recall and correct/incorrect abstentions, not just case accuracy.
5. Intent evaluation includes semantic-slot precision/recall/F1 and literal-evidence grounding.
6. Context reporting shows whether critical discourse/reference evidence survived the actual prompt-budget path.
7. Mechanics routing and decision-family metrics are separate from deterministic dice/result correctness.
8. Planner evaluation reports operation precision/recall, duplicate/unsupported output and final persistent changes.
9. Critical negative controls have zero false persistent changes; secret leakage is zero; critical identity/attribution/abstention/correction violations are zero.
10. Critical cases run three times and any critical mismatch fails the live gate.
11. Normal CI stays offline/deterministic; live Ollama tests remain explicitly marked `real_llm`.
12. CI, Ruff, both Pyright scopes, JavaScript tests and CodeQL pass on the final PR head.
13. Documentation records the exact first baseline and distinguishes deterministic contracts from live model and SillyTavern acceptance.

This PR does not by itself certify SillyTavern acceptance. A manual integration pass remains a separate gate after the live corpus is clean.

## 7. Non-goals

- No new LLM agent/role or independent per-field interpretation call.
- No changes to `PlayerIntentAnalysis v2` unless a measured corpus failure proves the typed contract insufficient; any schema change needs a separate compatibility review.
- No changes to mechanics rules, dice authority, domain write authority or persistence lifecycle.
- No vector database, embeddings, generic memory layer, provider retry policy, model switching or new infrastructure without measured evidence.
- No broad rewrite of `TurnResolutionService` or planner prompt architecture in this evaluation tranche.
- No benchmark claim based solely on fixture count, parser validity, deterministic CI or one passing sample.

## 8. Validation commands

Deterministic corpus/resolver/integrity, discourse builder, prompt and mechanics-context tests:

```bash
python -m pytest \
  tests/test_semantic_evaluation_corpus.py \
  tests/test_conversation_reference_holdout.py \
  tests/test_discourse_pipeline_holdout.py \
  tests/test_discourse_context_builder.py -q
```

Focused deterministic pipeline tests:

```bash
python -m pytest \
  tests/test_discourse_context_builder.py \
  tests/test_conversation_reference_resolver.py \
  tests/test_modular_language_pipeline.py \
  tests/test_pending_intent_correction_flow.py -q
```

Opt-in live discourse, correction and integrated-pipeline evaluation:

```bash
CAMPAIGN_MANAGER_REAL_LLM_MODEL=<pinned-model-tag> \
CAMPAIGN_MANAGER_REAL_LLM_BASE_URL=http://localhost:11434 \
CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT=120 \
python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -v -s
```

Full deterministic CI remains:

```bash
python -m pytest -m "not real_llm" --cov --cov-report=term-missing
ruff check .
pyright
```

Record model digest per role, Ollama server version, model settings, hardware, source commit, test IDs, repetitions, per-stage metrics, provider-call counts, tokens, latency, repair use and final operation types. Never commit a claimed live pass without its reproducible evidence.

## 9. Durable continuation checkpoint

This section is the source of truth when work is interrupted.

### Current checkpoint

- **Branch:** `feat/227-held-out-discourse-pipeline-evaluation`
- **Base:** `main` at `61725a03346d2ebfcf0ce6b2aacf92c0b6789b28`, containing the PR #226 merge.
- **PR:** [#227 — held-out discourse and staged pipeline evaluation](https://github.com/IvanVM04/Campaign-Manager/pull/227); open, Draft, base `main`.
- **Branch tip:** resolve the live SHA from the PR head or branch URL when resuming; do not pin a self-referential hash inside this checkpoint.
- **WP0:** complete. Branch, execution spec, Draft PR and documentation links are in place.
- **WP1:** complete. The new `discourse_pipeline_corpus_holdout_v1.json` contains 28 Spanish-first scenarios across seven balanced families. Integrity tests prove family balance, stable IDs, normalized input uniqueness and cross-held-out ID uniqueness.
- **WP2:** complete. `test_discourse_pipeline_holdout.py` exercises topic/callback scoping, quote-safe discourse markers, ellipsis cues, twelve-turn history, local grammar, NPC attribution, reference links/abstentions and correction evidence separation. A false-positive fix in `DiscourseContextBuilder` ignores control phrases that occur only inside quoted speech.
- **WP3:** live harness implemented, not executed here. `test_real_llm_discourse_pipeline.py` evaluates 24 non-correction cases through the actual Intent Interpreter, sends the same analysis to deterministic reference resolution, scores intent/action-frame/argument slots and records family-level prompt/discourse retention and usage metadata. Critical cases repeat three times. Another opt-in test evaluates evidence-bound multi-round corrections.
- **WP4:** implementation complete for this tranche. Deterministic tests verify NPC discourse reaches the Intent prompt and Mechanics receives only active-step canonical references. Live evaluation records context retrieval recall and discourse-index retention/omission. The integrated failed-action probe records all role metrics and mechanics routing.
- **WP5:** implementation complete for this tranche; live acceptance pending. The negative integrated probe exercises Intent → Resolution → Mechanics → Planner, a failed deterministic roll, blocked conditional progression and zero persistent operations. The positive integrated probe exercises a completed observation → Intent → Resolution → Planner, asserts exactly one explicit update to known NPC `Aldric`, no duplicate create, and Mechanics skipped. Both collect operation and per-role metrics. The original #226 probe remains independent.
- **WP6:** documentation and reporting implementation complete. The prompt-evaluation guide, 138-case corpus inventory (50 development + 88 held-out), AI roadmap and docs hub are synchronized. Live Ollama baseline and SillyTavern acceptance are not claimed.
- **Latest code/test files:** `tests/fixtures/discourse_pipeline_corpus_holdout_v1.json`, `tests/test_discourse_pipeline_holdout.py`, `tests/test_real_llm_discourse_pipeline.py`; updated `services/discourse_context.py`, `tests/test_discourse_context_builder.py`, and `tests/test_semantic_evaluation_corpus.py`.
- **Current CI:** inspect the Tests and CodeQL runs attached to the current PR head. Earlier Ruff findings (unused imports and one unused binding) were corrected; do not mark the newest head green until its complete workflows pass.
- **Next exact action:** fix any CI failure on the newest head. After deterministic CI is green, run `python -m pytest tests/test_real_llm_discourse_pipeline.py -m real_llm -v -s` using the pinned local Ollama model, then save model digests/settings and per-family results. Do not tune prompts before saving that baseline.
- **Live acceptance not executed here:** no local Ollama endpoint/model, digest, hardware or sampling settings were available in this GitHub-only session. The manual SillyTavern lifecycle test is also separate and still pending.
- **Resumption rule:** when asked to continue PR #227, inspect this checkpoint, current branch head, PR status and CI first. Continue from the first unchecked acceptance task; do not recreate the branch or repeat completed inventory.
### Estimated implementation effort

| Work package | Estimate |
|---|---:|
| WP1 — corpus gap analysis, fixture and integrity checks | 2–3 h |
| WP2 — deterministic evaluation harness | 2–3 h |
| WP3 — live intent/discourse scoring | 2–4 h |
| WP4 — context/mechanics evaluation | 2–3 h |
| WP5 — planner and integrated live subset | 2–4 h |
| WP6 — reporting, docs, CI and fixes | 1–3 h |
| **Total active effort** | **11–20 h** |

The first clean baseline run and report should sit toward the lower end. Model-driven mismatches requiring prompt changes and reruns will push toward the upper end. Local inference wall time depends on the configured model and hardware.

## 10. Recommended execution order after preparation

1. Freeze the corpus schema and prove there are no duplicates with the existing held-out fixtures.
2. Implement deterministic fixture integrity and resolver scoring before adding live calls.
3. Add the live Intent/Discourse evaluator and capture an unchanged-prompt baseline.
4. Add context/mechanics stage measurements and only then proposal/integrated evaluation.
5. Review the per-family failure report. Make evidence-backed prompt or resolver changes only after saving the baseline.
6. Re-run the complete critical subset after any prompt change; preserve the old baseline as a comparison artifact.
7. Complete documentation and CI, then hand off the local Ollama commands/results for acceptance.


### Remaining acceptance estimate after implementation

- Final deterministic CI/fix pass: 0.5–2 h depending on any newly exposed failures.
- Pinned local Ollama evaluation and per-family report: 2–4 h active time, excluding model inference latency.
- Manual SillyTavern acceptance is a separate 1–2 h gate; it remains outside the deterministic harness and is not claimed here.

No live pass is claimed until the actual model has run and its digest, generation settings, hardware and per-family results have been recorded.
