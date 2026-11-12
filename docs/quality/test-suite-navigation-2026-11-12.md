# Test-suite navigation — 2026-11-12

**Baseline:** `main` after PR #204, commit `73b6fc627e4cf94cea5bb8ad97c36f596567c8dc`.  
**Change set:** PR #205 reorganizes two large test modules. It changes test placement and shared fixture support only; application/runtime code and assertions are unchanged.

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

## Next coverage priorities

1. **Provider contract matrix:** success, timeout, unavailable Ollama, malformed response and normalized error behavior. Keep retry ownership explicit between provider and caller.
2. **Campaign runtime lifecycle:** invalidation after campaign deletion/configuration changes, shutdown semantics and safe cache bounds for the supported one-process deployment.
3. **Critical transaction branches:** rollback after partial writes, stale revisions, lease fencing, restart recovery and campaign-time effect expiry.
4. **Context scale probes:** representative medium/large campaign fixtures, stable ranking and budget exhaustion. Add live Ollama probes only as opt-in acceptance work.

No test deletion or production behavior change is part of this reorganization.
