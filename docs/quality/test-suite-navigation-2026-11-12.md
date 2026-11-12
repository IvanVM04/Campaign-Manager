# Test-suite navigation — 2026-11-12

**Baseline:** `main` after PR #208, commit `96b0232395de670d4ef4c4fa658eae88dd8f3c34`.  
**History:** PR #205 reorganized the durable-turn and context suites without changing production behavior. PRs #207 and #208 subsequently added scale/proposal probes and structured observability. This page retains the original split details and adds the current quality/acceptance map.

## Durable turn lifecycle

The former `tests/test_durable_native_turn_service.py` contained 24 test functions spanning two separate public workflows. It is now separated by client contract:

| Module | Test functions | Protected behavior |
|---|---:|---|
| `tests/test_durable_native_turn.py` | 12 | Native commit-before-narration, idempotent replay, narration recovery, manual-roll challenge, clarification continuation, planning lease release/fencing, restart recovery and conflicting idempotency keys. |
| `tests/test_durable_silly_tavern_turn.py` | 12 | External turn identity, resolve/complete, swipe/transcript versioning, duplicate delivery, clarification, manual-roll state recovery and conflicting/skipped transcript versions. |
| `tests/durable_turn_test_support.py` | — | One deterministic fake-provider runtime builder shared by both modules; not collected as a test module. |

The split preserves all 24 original test functions. The native and SillyTavern tests still exercise the real durable application service; only provider calls are deterministic/injected. The support module is deliberately not named `test_*.py`.

## Adapter and effects boundaries

| Module | Protected behavior |
|---|---|
| `tests/test_silly_tavern_context_adapter.py` | SillyTavern context query validation, campaign-state error mapping, recent-turn filtering, optional session/character projection, external transcript version state and façade delegation. |
| `tests/test_effects_api.py` | Persistent-effect API create/list/status/remove lifecycle, payload mapping and 404/409/422 error contracts. |
| `tests/test_silly_tavern_api.py` | SillyTavern integration endpoint success, request validation and sanitized error mapping for context, turn state, clarification, manual rolls, resolution and narration completion. |
| `tests/test_persistent_effect_api_schemas.py` | Permanent, conditional, campaign-time and encounter duration shapes; strict numeric bounds; canonical condition/exhaustion rules; narrative slug constraints. |

## Context pipeline

The former `tests/test_context_pipeline.py` contained 35 test functions for retrieval, security, budget and result-purity contracts. It is now grouped by observable behavior:

| Module | Test functions | Protected behavior |
|---|---:|---|
| `tests/test_context_pipeline_retrieval.py` | 21 | Query normalization/validation, direct and related entity selection, relationship expansion, inactive records, secret/public event filtering and parent item/resource resolution. |
| `tests/test_context_pipeline_budget.py` | 6 | Character budget, oversized candidate handling, public result schema and exclusion of internal ranking diagnostics. |
| `tests/test_context_pipeline_integrity.py` | 8 | No mutation of canonical/nested world state, deterministic output/order, empty results, relation metadata rendering and result isolation. |
| `tests/context_pipeline_test_support.py` | — | Shared deterministic entity/world fixture builders; not collected as a test module. |

All 35 original test functions and their assertions are preserved. The support module owns only reusable fixture construction; each test remains next to the contract it protects.

## Prompt and model evaluation

- Deterministic prompt contracts remain in `tests/test_llm_world_proposal_prompt_builder.py`, `tests/test_llm_world_proposals.py`, `tests/test_proposal_scale_quality.py` and `tests/test_context_scale_probes.py`.
- `tests/test_real_llm.py` is opt-in and calls local Ollama. Run `python -m pytest -m real_llm -v -s`; see [the prompt evaluation guide](prompt-evaluation-2026-11-12.md).
- Never make the CI suite depend on Ollama or compare exact generated prose. Live probes assert semantic invariants and remain separate from the SillyTavern UI smoke test.

## Rules for future test organization

- Split by externally observable contract or independently meaningful boundary, not by arbitrary line count.
- Keep multi-aggregate rollback, restart/recovery and concurrency tests intact when moving them.
- Share only deterministic fixture construction; do not hide assertions inside support utilities.
- Keep `real_llm` probes separate from deterministic CI. A green deterministic run does not validate Ollama model quality or the live SillyTavern extension.
- Do not add a global coverage threshold solely to force the percentage upward. Use branch coverage to select missing failure paths.

## Current quality baseline and next gate

The latest main coverage artifact (2026-11-12, after PR #208) reported 86.8% line coverage, 73.6% branch coverage and 83.4% combined line/branch coverage. The quality branch reaches 89.3% line, 76.3% branch and 85.98% combined coverage, and now enforces `fail_under = 85` with branch coverage enabled.

The highest-return additions target the SillyTavern context adapter, persistent-effect API/schema validation and the manual-roll submission lifecycle. Manual rolls are now tested through successful submission, idempotent replay, completion, interrupted prepared-state recovery and stale-context rejection.

Keep the 85% gate; do not exclude production modules or weaken assertions to preserve it.

Next acceptance gates:
1. **Coverage and prompt contract PR:** reach 85% combined line/branch coverage, document the live prompt corpus and keep all deterministic CI checks green.
2. **Live Ollama evaluation:** run the opt-in manual probes and record backend revision, Ollama/model tag and results.
3. **SillyTavern acceptance:** run the separate manual checklist and record extension/backend revisions. Do not treat deterministic fake-provider tests as model-quality validation.

The synthetic context-scale and structured-proposal probes are implemented in
PR #207 and documented in
[context-scale-probes-2026-11-12.md](context-scale-probes-2026-11-12.md).
They cover large candidate sets, stable insertion-order behavior, budget
growth, mandatory facts, dependencies, non-mutation, secret filtering and a
single bounded repair. They do not replace live-model acceptance.

Already covered deterministically:
- Ollama request success, timeout, connection failure, HTTP errors with/without parseable error bodies, malformed/non-object JSON, malformed response payloads and no hidden transport retry.
- Fake provider fixed/prompt-selected responses, failure injection and observable prompt/call tracking.
- Campaign runtime reuse/isolation, selective invalidation, shutdown, idempotent shutdown and reconstruction after shutdown.

Campaign deletion/configuration-triggered invalidation and cache eviction remain deferred because those lifecycle requirements are not part of the current single-process product contract. Do not add TTL/LRU without measured cache pressure and an explicit in-flight request policy.

No test deletion or production behavior change was part of PR #205.
