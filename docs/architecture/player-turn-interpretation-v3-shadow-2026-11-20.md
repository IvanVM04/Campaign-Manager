# Player turn interpretation v3 — shadow prompt and v2 comparison

**Date:** 2026-11-20  
**Implementation PR:** #286  
**Architecture source:** [Player-intent semantic redesign audit — PR #282](player-intent-semantic-redesign-audit-2026-11-20.md)  
**Contract source:** [Player turn interpretation v3 — PR #285](player-turn-interpretation-v3-contract-2026-11-20.md)  
**Production route:** PlayerIntentAnalysis v2  
**Status:** The v3 prompt, response schema, strict decoder integration in the test harness and paired shadow runner are implemented as opt-in evaluation assets. Production still calls v2 only.

## 1. Purpose

PR #282 Phase 2 requires one holistic interpretation call that emits the entire v3 structure, evaluated in shadow mode against v2 using the same player evidence and the same bounded context. PR #285 supplies the additive DTO and strict decoder. This PR joins those two pieces for measurement; it does not activate v3 in the turn lifecycle.

The target question is not whether v3 returns more fields. It is whether it represents complete scenarios more accurately while avoiding extra events, false relations, incorrect quote attribution, unsupported facts and evidence-span errors.

## 2. Implementation

The evaluation-only implementation lives under tests/:

- tests/player_turn_interpretation_v3_shadow.py contains the v3 Spanish-first holistic system prompt, the response JSON Schema, context-preserving prompt builder and paired runner.
- tests/fixtures/player_turn_v3_shadow_corpus_v1.json contains 12 audit-derived held-out scenarios.
- tests/player_turn_v3_shadow_evaluation.py validates the fixture contract and scores exact structural labels/counts, including extra predictions as false positives.
- tests/test_player_turn_v3_shadow.py protects prompt framing, context preservation, evidence identity, budget failures, paired calls and failure isolation.
- tests/test_real_llm_player_turn_v3_shadow.py is the opt-in Ollama comparison. It records content-free metrics and an optional report.

### Paired call behavior

1. The runner clones the supplied IntentInterpreter with the same provider, context builder, prompt/context byte limits and normalization pipeline.
2. It calls the cloned v2 interpreter once and captures the exact rendered prompt in a transparent provider proxy. The proxy does not change the provider response or settings.
3. It replaces only the v2 instruction block with the v3 prompt. World projection, same-chat history, discourse hints, conversation block and exact current-player evidence are copied unchanged.
4. The prompt builder rejects ambiguous framing markers, evidence mismatches or a prompt exceeding the configured byte budget. It does not silently truncate the evidence or discard context.
5. The same provider receives one v3 structured response. The result is decoded by TurnInterpretationV3.from_json() against the exact current utterance.
6. The in-memory comparison contains typed v2/v3 outputs and timings, but no raw prompts or completions. The scorer projects it to counts, enum labels, mismatch field names and byte/time measurements.

If v2 fails validation after its prompt is built, v3 is still attempted for diagnostic comparison. If prompt framing or evidence checks fail, v3 is marked not_run. A v3 provider/decoder failure never replaces, edits or invalidates the v2 result.

## 3. Semantic coverage

The 12 held-out scenarios are based on the reference phenomena in section 8 of the PR #282 audit:

- NPC warning and quoted instruction versus player instruction;
- callback followed by a current attempt;
- conditional future action and its dependency;
- uncertain result of an attempted action;
- player dialogue followed by a separate examination;
- explicit directed kinship relation;
- transfer without inferred ownership;
- visible NPC attribute alongside a narrative event;
- attempted action with an expressed failure;
- explicit negation contrasted with a later decision;
- uncertainty about a reported statement.

The v2 gold records category, step count, active-step index, modality and actor axes, and relation-claim count. The v3 gold records node/evidence/quote cardinality; speaker and addressee mention presence; attributed event/fact source counts; utterance forces and speaker roles; event predicate surfaces and families, polarity, epistemic status and action phase; discourse-link types and endpoint kinds; callback anchors; fact kinds, relation families, direction, polarity, epistemic status, temporal scope, literal relation predicate surface and normalized relation type; and clarification kinds. Arrays are scored as multisets, so duplicate and unsupported labels are false positives. Exact cardinality checks expose extra and missing nodes/spans. The scorer does not award credit for extra labels or nodes.

These first gold annotations are an explicit diagnostic baseline. Any disputed annotation must be reviewed against the audit and resolved before interpreting aggregate scores. The fixture is separate from the prompt and is not injected into model context.

## 4. Safety and production boundary

- v2 remains the only production interpretation route and remains the only output available to mechanics, proposal generation and durable persistence.
- The v3 runner and v3 model imports remain under tests/; no production service or bootstrap imports models.player_turn_interpretation_v3.
- The v3 output is not converted into GameplayActionCandidate, is not passed to MechanicsAdjudicator or LLMWorldExtractor and cannot change world state.
- No v3 prompt, completion, player input, transcript, campaign context, entity names or evidence span text is written to logs or reports.
- Reports contain only the existing allowlisted provider metadata/usage and the benchmark's case IDs, family names, statuses, mismatch field names, aggregate metric counts, prompt sizes and durations. Raw mention strings, predicates, callback anchors and utterance text are used only for in-memory exact matching and are never emitted in reports or logs.
- Evidence is still validated by the strict PR #285 decoder. A valid JSON response that invents a span, reference or unsupported field is not considered a valid interpretation.
- The runner makes two sequential model calls per case. The extra latency and total VRAM/model load are part of the measurement and must be reported; v3 is not run in production.

## 5. How to run

Deterministic tests (no Ollama required):

    python -m pytest tests/test_player_turn_v3_shadow.py tests/test_player_turn_interpretation_v3.py -q

Opt-in live comparison:

    python -m pytest -m real_llm tests/test_real_llm_player_turn_v3_shadow.py -v -s

It uses the existing intent-provider configuration, including CAMPAIGN_MANAGER_REAL_LLM_MODEL, CAMPAIGN_MANAGER_REAL_LLM_BASE_URL, CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT and the role-specific intent settings. An optional single-case filter is available through CAMPAIGN_MANAGER_REAL_LLM_V3_SHADOW_SCENARIO_ID.

To write the content-free report, set CAMPAIGN_MANAGER_REAL_LLM_V3_SHADOW_REPORT_PATH to the desired local JSON path. The fixture remains held-out; do not add its exact utterances to the system prompt or copy it into development examples.

## 6. Interpretation of results and gates

The first live run is diagnostic, not a rollout gate. It must report v2 and v3 contract validity, per-family exact structural accuracy, precision/recall for each enum multiset, extra/missing nodes, v2/v3 prompt bytes, elapsed time and provider usage. Empty denominators remain unmeasured.

Do not use a single aggregate score to conceal regressions. In particular, improvements in callbacks or relation recall do not compensate for degraded quotes, negation, attribution, conditionals, transfer false positives or NPC facts. Critical citation/instruction and false-persistence controls require explicit review.

This PR does not approve a numerical live acceptance threshold. The audit requires thresholds to be fixed per dimension before examining the next official run; the provisional values in PR #282 are proposals, not current gates. The formal repeated live acceptance and SillyTavern decision remain in PR #289.

## 7. Explicit non-goals

- No production prompt switch or production import of v3.
- No mechanics/action selector, action dependency graph or durable checkpoint (PR #287).
- No world-fact eligibility policy, operation construction, schema migration or persistence (PR #288).
- No changes to model choice, temperature, quantization, number of model calls in production, parser dependencies or SillyTavern integration.
- No claim that Ollama live evaluation or manual SillyTavern acceptance has been run by this PR.
