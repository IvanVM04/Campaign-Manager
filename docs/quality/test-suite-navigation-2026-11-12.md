# Test-suite navigation — 2026-11-12

**Baseline:** `main` after PR #205, commit `a14d1568ba852cd545caaf06e9efd48a4f925b03`.  
**Change set:** PR #205 is merged. Its test-only reorganization changes test placement and shared fixture support; production behavior and assertions are unchanged.

## Durable turn lifecycle

The former `tests/test_durable_native_turn_service.py` contained 24 test functions spanning two separate public workflows. It is now separated by client contract:

| Module | Test functions | Protected behavior |
|---|---:|---|
| `tests/test_durable_native_turn.py` | 12 | Native commit-before-narration, idempotent replay, narration recovery, manual-roll challenge, clarification continuation, planning lease release/fencing, restart recovery and conflicting idempotency keys. |
| `tests/test_durable_silly_tavern_turn.py` | 12 | External turn identity, resolve/complete, swipe/transcript versioning, duplicate delivery, clarification, manual-roll state recovery and conflicting/skipped transcript versions. |
| `tests/durable_turn_test_support.py` | — | One deterministic fake-provider runtime builder shared by both modules; not collected as a test module. |

The split preserves all 24 original test functions. The native and SillyTavern tests still exercise the real durable application service; only provider calls are deterministic/injected. The support module is deliberately not named `test_*.py`.

## Context pipeline

The former `tests/test_context_pipeline.py` contained 35 test functions for retrieval, security, budget and result-purity contracts. It is now grouped by observable behavior:

| Module | Test functions | Protected behavior |
|---|---:|---|
| `tests/test_context_pipeline_retrieval.py` | 21 | Query normalization/validation, direct and related entity selection, relationship expansion, inactive records, secret/public event filtering and parent item/resource resolution. |
| `tests/test_context_pipeline_budget.py` | 6 | Character budget, oversized candidate handling, public result schema and exclusion of internal ranking diagnostics. |
| `tests/test_context_pipeline_integrity.py` | 8 | No mutation of canonical/nested world state, deterministic output/order, empty results, relation metadata rendering and result isolation. |
| `tests/context_pipeline_test_support.py` | — | Shared deterministic entity/world fixture builders; not collected as a test module. |

All 35 original test functions and their assertions are preserved. The support module owns only reusable fixture construction; each test remains next to the contract it protects.

## Rules for future test organization

- Split by externally observable contract or independently meaningful boundary, not by arbitrary line count.
- Keep multi-aggregate rollback, restart/recovery and concurrency tests intact when moving them.
- Share only deterministic fixture construction; do not hide assertions inside support utilities.
- Keep `real_llm` probes separate from deterministic CI. A green deterministic run does not validate Ollama model quality or the live SillyTavern extension.
- Do not add a global coverage threshold solely to force the percentage upward. Use branch coverage to select missing failure paths.

## Remaining coverage priorities after PR #205

1. **Context scale probes:** representative medium/large campaign fixtures, stable ranking, mandatory character/location retention, dependency expansion, budget exhaustion and projection non-mutation.
2. **Critical transaction branches:** continue targeting stale revisions, partial-write rollback, lease fencing/recovery and campaign-time effect expiry when a concrete uncovered path is identified.
3. **Live Ollama + SillyTavern acceptance:** run the opt-in manual checklist and record backend/extension revisions, model and settings. Do not treat deterministic fake-provider tests as model-quality validation.

Already covered deterministically:
- Ollama request success, timeout, connection failure, HTTP errors with/without parseable error bodies, malformed/non-object JSON, malformed response payloads and no hidden transport retry.
- Fake provider fixed/prompt-selected responses, failure injection and observable prompt/call tracking.
- Campaign runtime reuse/isolation, selective invalidation, shutdown, idempotent shutdown and reconstruction after shutdown.

Campaign deletion/configuration-triggered invalidation and cache eviction remain deferred because those lifecycle requirements are not part of the current single-process product contract. Do not add TTL/LRU without measured cache pressure and an explicit in-flight request policy.

No test deletion or production behavior change was part of PR #205.
