> **Historical document — superseded by the 2026-11-12 legacy-retirement cleanup.**
> The narrative-first extractor, static legacy prompt builder, deprecated
> `POST /integration/turn`, legacy turn service and runtime snapshot
> reconciliation described below have been removed. Migration 029 archives
> existing non-null snapshot JSON in `turn_snapshot_archive`. Do not treat
> the recommendations in this historical report as current implementation
> instructions; see [the current architecture audit](architecture-audit-2026-11-12.md)
> and [turn pipeline contract](turn-pipeline-compatibility.md).

# Legacy narrative extraction boundary audit — 2026-11-12

## Purpose

Record the remaining production consumers of the narrative-first extraction API before decomposing its large static prompt. This audit distinguishes the compatibility path from the active structured player-intent proposal path.

## Verified production call sites

| Consumer | Behavior | Disposition |
|---|---|---|
| `services/turns/turn_resolution_service.py` | Calls `LLMWorldExtractor.extract()` only on the narrative-first compatibility branch; the durable player-intent branch calls `propose()`. | Retain while the compatibility branch is supported. |
| `services/turns/legacy_silly_tavern_turn_service.py` | Calls `extract()` for the deprecated SillyTavern mutation route. | Retain with the deprecated route; removal requires the existing usage/deprecation gate. |
| `LLMWorldExtractor.__call__()` | Public callable facade delegates to `extract()`. | Preserve unless all callable consumers and the package API contract are intentionally migrated. |

The separately marked `tests/test_real_llm.py` exercises the legacy extraction contract against a live Ollama provider. It is a quality probe, not a production consumer, and remains outside deterministic CI.

Repository code search did not find additional production imports or direct `.extract()` calls. The old monolithic extractor test module was split by PR #193 into explicit legacy-extraction and structured-proposal modules; all 36 test functions were retained.

## Prompt ownership and decomposition plan

The 46,851-character `services/llm_world/llm_world_prompt_builder.py` remains a compatibility prompt builder. It is not used to assemble the active durable player-intent proposal prompt. Do not shorten it or remove instructions merely to reduce source size.

A follow-up behavior-preserving refactor should:

1. Keep `LLMWorldPromptBuilder.build_prompt(text, context)` as the stable public façade.
2. Move static instruction content into cohesive, independently named sections: role/output safety; confirmed facts and identity; entities/relations; items/instances/inventory; resources/events; and output schema/examples.
3. Keep dynamic world context rendering in `LLMWorldContextRenderer`; do not duplicate renderer responsibilities inside static sections.
4. Assemble sections in an explicit, documented order without silently dropping or rewriting rules.
5. Add a regression assertion that the assembled prompt is byte-for-byte identical to the pre-refactor output for representative contexts before considering any quality-driven wording change.
6. Keep legacy prompt tests in `test_llm_world_legacy_extraction.py`; keep proposal prompt tests in `test_llm_world_proposals.py`.
7. Only after behavior-preserving extraction is green, use representative Ollama quality probes to evaluate deliberate prompt changes. A source split alone does not reduce tokens sent to the model.

## Explicit non-goals

- No changes to extraction semantics, operation schemas, parsing, model provider, context projection or domain validation.
- No removal of the legacy SillyTavern route, snapshot compatibility or `extract()` API.
- No claims that prompt text is authorization; deterministic application validation remains authoritative.
- No reduction of test count or deletion of assertions.

## Merge gates

- All 52 reorganized test functions are collected.
- Ruff and import sorting pass.
- Deterministic Python suite, required Pyright scopes, JavaScript tests and both CodeQL checks pass.
- No runtime behavior changes appear in the diff.
- Live Ollama/SillyTavern smoke tests are reported separately from deterministic CI.



## Revalidation after the bounded-context change — PR #197

The production call sites still use the same `LLMWorldExtractor.extract()` API. The composition root injects `ContextBuilder.build_relevant_world_projection()`, so the narrative-first compatibility branch in `TurnResolutionService` and the deprecated SillyTavern processor share the same selection and budget behavior without importing context services into the LLM package.

The selector:
- uses the narrative as its deterministic search query;
- requires the active character and current location when those entities exist;
- includes dependencies for selected relations, events, item instances and resource balances;
- uses the public memory export/search path, which excludes secret events;
- returns a detached projection and does not mutate canonical `WorldState`.

The extractor enforces separate selected-record and complete-prompt budgets before calling the provider. Selection failures and prompt overflow fail closed. Direct extractor construction without an injected selector remains source-compatible, but still has a hard total-prompt cap.

The static instruction text remains unchanged and the existing rendered-prompt golden fixture is preserved. This PR closes the unbounded dynamic-context/prompt-submission gap; it does not claim that the 46,851-character static prompt has been optimized. A future prompt-simplification change requires representative live Ollama quality probes.
