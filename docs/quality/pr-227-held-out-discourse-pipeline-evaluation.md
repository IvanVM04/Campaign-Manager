# PR #227 — Held-out discourse and staged pipeline evaluation

**Status:** Draft PR #227 opened; preparation slice committed; runtime implementation has not started.  
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
- [ ] Link this work from the active evaluation guide and roadmap.

### WP1 — Corpus gap analysis and fixture design
- [ ] Map every proposed case to an uncovered behavior from PR #223 or a missing stage-level contract after PR #226.
- [ ] Confirm no normalized utterance duplicates any of the existing 110 held-out scenarios.
- [ ] Implement the 28-case discourse/pipeline fixture with 7 balanced families.
- [ ] Mark critical false-positive/abstention/correction controls and document why each is critical.
- [ ] Add integrity checks for schema, stable IDs, family counts, history bounds, normalized uniqueness and prompt-holdout isolation.

### WP2 — Deterministic evaluation harness
- [ ] Drive the real discourse builder and deterministic conversation/world resolvers from fixture histories/visible world states.
- [ ] Score link precision/recall and correct/incorrect abstentions by family.
- [ ] Cover callback scoping, the twelve-turn boundary, plural abstention, NPC attribution evidence and corrections without making live-model assumptions.
- [ ] Keep deterministic resolver contract tests independent from Ollama.

### WP3 — Live intent and discourse evaluation
- [ ] Evaluate the Intent Interpreter using each scenario's current input and bounded recent history.
- [ ] Score the expected semantic invariants and slot multiset (including unsupported extras) by family.
- [ ] Record attribution, topic/callback and history evidence metrics separately from basic intent accuracy.
- [ ] Repeat critical cases three times; retain every mismatch and provider/decoder failure.
- [ ] Record exact role model/tag/digest, Ollama version, generation parameters, timeout, hardware, run SHA, calls and per-role latency/token counts.

### WP4 — Context and mechanics stage evaluation
- [ ] Evaluate selected canonical context retrieval for active-step references, required visible facts and forbidden secret markers.
- [ ] Make discourse/context compaction observable: distinguish selected, retained, compacted and omitted signals without exposing their content.
- [ ] Assert mechanics call routing for actionable attempts versus questions, plans, negation, ambiguity and completed observations.
- [ ] Score decision family only where a mechanics call is expected; deterministic dice/result authority remains untouched.

### WP5 — Consequence planner and integrated pipeline subset
- [ ] Evaluate a curated subset through the real proposal role using the exact shared analysis, trusted references and confirmed mechanics outcome.
- [ ] Measure operation-family precision/recall, duplicates, conditional progression, false persistent changes and secret leakage.
- [ ] Add a smaller full-orchestrator live subset that exercises intent → resolution → mechanics → planner with stage-specific result properties.
- [ ] Ensure failed prerequisites and non-actionable/quoted/negative cases never produce unsupported persistent consequences.
- [ ] Preserve the #226 probe as an independent regression.

### WP6 — Reporting, documentation and handoff
- [ ] Emit a reproducible per-stage/per-family report and machine-readable test properties.
- [ ] Update the prompt-evaluation guide, corpus index and AI-understanding roadmap with exact fixture/test names and acceptance boundaries.
- [ ] Record the first pinned-model baseline; do not claim a pass until the user runs the configured local Ollama model.
- [ ] Synchronize this checkpoint and provide the exact commands, current head and next action.

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

Deterministic corpus/resolver/integrity tests (names may be refined when WP1/WP2 are implemented):

```bash
python -m pytest \
  tests/test_semantic_evaluation_corpus.py \
  tests/test_conversation_reference_holdout.py \
  tests/test_discourse_pipeline_holdout.py -q
```

Focused deterministic pipeline tests:

```bash
python -m pytest \
  tests/test_discourse_context_builder.py \
  tests/test_conversation_reference_resolver.py \
  tests/test_modular_language_pipeline.py \
  tests/test_pending_intent_correction_flow.py -q
```

Opt-in live discourse/pipeline evaluation (expected new test module; finalize exact selector during WP3):

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
- **Current branch head at preparation checkpoint:** `577ed60be63d028639bfcc6f1cfb4ee6a93114de`.
- **Documentation synchronization:** corrected the historical PR #226 execution checkpoint to reflect its merge into main, final deterministic workflow results and remaining post-merge live acceptance.
- **Current implementation status:** WP0 complete (branch, execution specification, four documentation links and Draft PR); no runtime code, new fixture cases or evaluator implementation has been started.
- **Completed audit:** existing baseline confirmed as 26 intent held-out + 20 semantic-frame held-out + 14 conversation resolver held-out = 60 held-out, plus 50 development scenarios. Live held-out tests currently evaluate intent/frame and one pending-recipient correction; no dedicated live discourse pipeline corpus exists.
- **Open work:** WP1–WP6 above.
- **Next exact action:** start WP1. Reconcile the proposed 28 cases against all current held-out fixtures, write the fixture schema and seven-family case matrix, then add the JSON fixture and integrity/de-dup tests. Do not tune prompts before the first held-out baseline is run.
- **Resumption rule:** when asked to continue PR #227, first inspect this checkpoint, current branch head, PR status and CI. Continue from the first unchecked work package; do not recreate the branch or repeat completed inventory.

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
