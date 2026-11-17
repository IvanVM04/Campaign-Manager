# Semantic-understanding evaluation corpus — 2026-11-13

**Foundation:** PR #220 introduced the 110-scenario corpus; PR #222 extends semantic-slot scoring and PR #227 adds a separate 28-case held-out discourse/pipeline tranche (138 scenarios total).  
**Baseline:** `main` before PR #222, `fd3e90039cc2f3409bec3917f5a34cc7bdaca696`  
**Priority:** P0 — measurement before prompt or retrieval expansion.

## 1. Purpose

The language pipeline now has a versioned shared intent contract, semantic action frames, directed relation claims, and an evidence-backed conversation resolver. The previous labelled sample was too small to distinguish a real improvement from a prompt-tuning regression.

This phase expands the evaluation set and reserves unseen utterances for measurement. It does not change provider prompts, the semantic schema, retrieval ranking, or domain authority. The held-out cases must not be copied into few-shot examples or prompt instructions.

## 2. Corpus inventory

The integrated corpus now contains 138 distinct scenarios: the original 110-case baseline plus 28 new PR #227 held-out discourse/pipeline cases.

| Evaluation layer | Development | Held-out | Total |
|---|---:|---:|---:|
| Utterance / intent analysis | 34 | 26 | 60 |
| Action frames / directed relations | 10 | 20 | 30 |
| Conversation reference resolution | 6 | 14 | 20 |
| Discourse and staged pipeline | 0 | 28 | 28 |
| **Total** | **50** | **88** | **138** |

The held-out fixtures are separate files:

- `language_understanding_corpus_holdout_v1.json`
- `semantic_frame_corpus_holdout_v1.json`
- `conversation_understanding_corpus_holdout_v1.json`
- `discourse_pipeline_corpus_holdout_v1.json` (PR #227; seven families with four cases each)

Each held-out file declares `split: held_out`, has stable scenario IDs and includes a family label. The deterministic corpus-integrity test checks the total count, unique IDs, unique held-out utterances and metadata. Do not move these cases into prompts, provider schema examples or tuning examples.

### Scenario families

The utterance tranche covers attempted actions, questions, plans/conditionals, observations and reports, negation/failure, explicit corrections, compound actions, epistemic uncertainty and quoted speech.

The semantic-frame tranche covers transfer roles, item-definition/instance distinction, movement source/path/destination, combat patient/instrument, containment, perception/instrument, directed relation types, negative/reported relations and temporal expressions.

The original conversation tranche covers player-authored focus, narrator-only evidence, speaker precedence, demonstratives, same-object references, other-role references, repeated topics, recency, the twelve-turn window, ambiguity and visibility-based abstention. PR #227 adds 28 separate discourse/pipeline cases covering topic boundaries, explicit callbacks, ellipsis/pending-action continuity, long-distance references/recency, local agreement, NPC attribution/quoted speech and multi-turn corrections.

The corpus is Spanish-first. Existing English cases remain in the development corpus as cross-language controls. The new held-out tranche does not claim broad multilingual coverage.

## 3. Scoring contract

`tests/semantic_evaluation_metrics.py` provides a provider-agnostic ledger. Live intent/frame evaluation records, per family:

- case accuracy;
- expected-slot recall;
- mean provider latency;
- total scenarios and provider calls.

The conversation hold-out suite additionally reports entity-link precision/recall and correct versus incorrect abstentions. A candidate that should remain unresolved must not be counted as a successful link.

The ledger also exposes recorders for context recall, operation precision/recall, critical false persistent changes and secret visibility. PR #222 adds multiset-based semantic argument/relation precision, recall and F1 so duplicate or unsupported model slots count as false positives. The deterministic projection test uses a 750-entity synthetic world to prove mandatory visible entities survive selection and secret event markers stay out of rendered model context. The live operation-quality test adds positive controls (a genuinely new fact on a known NPC and an explicitly introduced NPC) and critical negative controls (failed attempt on a known locked door, ephemeral observation, conditional plan, negation, question and quoted instruction). These are deliberately separate from parser slot accuracy: a correctly parsed utterance does not prove retrieval quality or safe consequences.

## 4. Quality-gate policy

- Corpus integrity and deterministic resolver tests run in ordinary CI.
- Live Ollama tests remain marked `real_llm`; normal CI must not depend on a local model.
- Critical held-out cases are repeated three times. Any critical interpretation/role/relation mismatch fails the live gate.
- Non-critical cases are measured and reported without inventing a pass threshold before the first full baseline is recorded.
- Per-family results must remain visible. An aggregate score must not hide a weak family.
- Keep model tag, provider-call count and total/mean latency in test properties.
- A model/schema parse failure is a failed scenario, not a silently skipped sample.

This is a measurement gate, not a claim that the corpus already passes on `gemma4:26b`. Run with a pinned model digest and recorded Ollama generation settings before setting family-specific targets.

## 5. Non-negotiable negative controls

Questions, future plans, conditionals, uncertainty, rumours, quotations, negations and failed attempts must not be upgraded to confirmed world facts. The operation layer remains the authority for writes; a semantic frame or relation claim is only evidence.

Operation evaluation in this tranche pairs positive controls with negative controls and reports:

- operation precision/recall by operation family;
- false persistent changes on critical negative controls (required: zero);
- secret leakage into the model-visible projection/prompt (required: zero);
- retrieval/context recall against the explicitly expected visible facts;
- provider latency and repair/call count.

Do not claim operation safety from intent-slot accuracy. The existing real-model operation regressions remain necessary and must stay green.

## 6. What this phase does not solve

- The guarded model-driven correction lifecycle is now integrated by PR #221 for pending durable clarifications. PR #222 adds an opt-in live Ollama regression for a corrected recipient; no live pass is claimed until that test is run with the pinned local model.
- PR #223 adds bounded ellipsis cues, explicit topic callbacks, a twelve-turn history window, local grammatical agreement and labelled NPC speaker extraction. These are constrained heuristics/evidence contracts, not general discourse parsing; live quality for them remains unmeasured.
- A literal temporal expression is not a normalized interval or event-time model.
- The original 110 scenarios remain the comparable baseline; the 28 PR #227 additions broaden discourse/pipeline coverage but are still a controlled sample, not proof of human-level understanding or broad language coverage.
- No embeddings, vector database or additional provider call is justified by corpus size alone. Measure deterministic retrieval first.

## 7. Execution

Deterministic checks:

```bash
python -m pytest tests/test_semantic_evaluation_corpus.py tests/test_conversation_reference_holdout.py -q
```

Opt-in live model evaluation:

```bash
CAMPAIGN_MANAGER_REAL_LLM_MODEL=<pinned-model-tag> python -m pytest -m real_llm tests/test_real_llm_semantic_holdout.py -v -s
```

Record the exact model digest, Ollama version, timeout, temperature/top-p/seed where supported, hardware, run SHA and the complete per-family output. Keep failed utterances and mismatches intact as regression evidence.


## 8. PR #223 discourse gap and PR #226 pipeline status

The original 110-case corpus predates the advanced discourse implementation. PR #223 added deterministic discourse behavior; PR #226 separated production Intent, Mechanics and Consequence Planner roles. PR #227 now adds a distinct 28-case held-out tranche and deterministic harness, plus opt-in live evaluators for Intent/resolution/context, ellipsis action recovery, prompt-level NPC speaker-hint retention, multi-turn corrections, a positive NPC-fact update and a negative failed-compound-action control. The live tests report by family and stage; they remain unexecuted until the pinned local Ollama model is supplied. History-derived NPC hints remain DiscourseEvidence; they are not written into `IntentStep.attributed_to`, which is grounded in current player evidence.

Do not fold the new cases into prompt examples or the original 110-case corpus. The complete 138-scenario inventory is 50 development + 88 held-out cases. Prompt retention and context retrieval are measured without logging their content. See the [PR #227 execution specification](pr-227-held-out-discourse-pipeline-evaluation.md) and the [independent audit](language-understanding-audit-2026-11-14.md).

## Predicate-specific evaluation (PR #250)

The 20-case semantic-frame held-out corpus is schema version 2. Each expected action frame and directed relation includes a case-sensitive `predicate` field copied from the current utterance. Live metrics separate `action_frame_predicate_surface` and `relation_predicate_surface` from semantic frame family, argument roles, relation direction and epistemic fields.

These metrics measure exact written-form preservation, not full lexical-sense disambiguation. Keep the dimensions separate when interpreting results: a predicate can be copied correctly while its frame or roles are wrong, and a correct frame family cannot compensate for a wrong predicate. See [PR #250 predicate evaluation and telemetry](pr-250-predicate-evaluation-and-telemetry.md).
