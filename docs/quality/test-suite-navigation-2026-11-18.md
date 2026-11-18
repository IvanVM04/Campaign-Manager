# Test-suite navigation — 2026-11-18

**Code baseline:** `f4fb3914ebab4579118863796e6f6d4b7183d0cf` (PR #255).  
**Documentation baseline:** `4a3a2549bb0bb1bc38ec0e6f456ac6d5ccef24d1` (PR #257).  
**Purpose:** route maintainers to the smallest useful tests while keeping cross-component recovery and security contracts covered.

## Current quality evidence

The latest documented deterministic run for the current code baseline reports:

- 2,042 passed, 22 deselected (opt-in `real_llm` tests).
- 85.14% combined coverage against an 85% gate.
- Ruff, JavaScript, required-scope Pyright, repository-wide Pyright and CI summary passing.
- CodeQL Python and JavaScript/TypeScript analyses passing.

The 22 deselected tests do not imply a live Ollama holdout passed. CI deliberately does not start Ollama. A manual SillyTavern session is a separate acceptance gate. See the [quality roadmap](quality-roadmap-2026-11-18.md).

## Test navigation by contract

| Contract | Primary tests/support | What they protect |
|---|---|---|
| Durable native turn | `tests/test_durable_native_turn.py`, `tests/test_durable_turn_*`, `tests/durable_turn_test_support.py` | Durable request identity, lifecycle, challenges, retries, commit, narration and recovery. |
| Durable SillyTavern | `tests/test_durable_silly_tavern_turn.py`, `tests/test_silly_tavern_*`, `tests/test_silly_tavern_context_adapter.py` | resolve/complete, external identity, conversation/chat isolation, versioning, clarification/manual roll and adapter projections. |
| Modular language pipeline | `tests/test_modular_language_pipeline.py`, `tests/test_player_intent_analysis.py`, `tests/test_semantic_frames.py`, `tests/test_intent_speech_act_contract.py` | Separate intent/mechanics/proposal roles, V1/V2 compatibility, evidence, semantic frames, modalities and actionability. |
| Discourse/reference resolution | `tests/test_discourse_context_builder.py`, `tests/test_conversation_reference_resolver.py`, `tests/test_conversation_reference_holdout.py`, `tests/test_entity_reference_resolver.py`, `tests/test_world_reference_resolver.py` | Topic/callback signals, pronouns, actor/speaker signals, entity identity, visibility, recency and abstention. |
| Compound player intent | `tests/test_compound_intent_evaluation.py` and fixture gold under `tests/fixtures/compound_intent_*` | Ordered per-step actor, modality, polarity and omission/extra-step regression. Live model score remains separate. |
| Semantic evaluation | `tests/semantic_frame_evaluation.py`, `tests/test_semantic_evaluation_corpus.py`, `tests/test_semantic_evaluation_metrics.py`, `tests/test_real_llm_semantic_holdout.py`, and predicate gold sidecar under `tests/fixtures/semantic_frame_predicate_gold_v1.json`. The language-understanding corpora are fixtures at `tests/fixtures/language_understanding_corpus_v1.json` and `tests/fixtures/language_understanding_corpus_holdout_v1.json`. | Held-out analysis, action/relation predicate scores, field-level diagnostics and privacy-safe reports. |
| Pending correction | `tests/test_pending_intent_correction.py` and `tests/test_pending_intent_correction_flow.py` | Literal answer evidence, immutable edits, preservation of unaffected fields, multi-round durable continuation. |
| Context retrieval | `tests/test_context_builder.py`, `tests/test_context_expander.py`, `tests/test_context_ranker.py`, `tests/test_context_renderer.py`, `tests/test_context_pipeline_*`, `tests/test_context_scale_probes.py` | Retrieval/expansion/ranking, budget, mandatory facts, record dependencies, stable order and no hidden state leakage. |
| World operations and visibility | `tests/test_entity_operation.py`, `tests/test_world_*`, `tests/test_memory_*` | Typed parsing/application, semantic validation, atomicity, read projections, secret-event filtering and export. |
| Character/campaign | `tests/test_campaign_*`, `tests/test_character_*`, `tests/test_hit_dice_rules.py`, `tests/test_campaign_clock_*` | Campaign scope, runtime lifecycle, character sheets, rest/Hit Dice and fictional clock. |
| Combat/rules | `tests/rules_engine/test_*.py`, `tests/test_combat_*`, `tests/test_attack_profile_resolver.py`, `tests/test_effect_condition_integration.py` | Pure mechanics, attack profiles, damage, canonical HP, movement, reactions, effects and transactional combat. |
| Persistence/migrations | `tests/test_database.py`, `tests/test_migrations.py`, `tests/test_*repository*.py` | Fresh schema, forward upgrades, constraints, indexes, triggers, rollback and campaign isolation. |
| API/architecture | `tests/test_api_*.py`, `tests/test_architecture_boundaries.py`, `tests/test_canonical_service_import_boundaries.py` | Transport contracts, error envelope, dependency direction and retired-path absence. |
| Provider/configuration | `tests/test_ollama_provider.py`, `tests/test_llm_settings.py`, `tests/test_llm_provider.py` | Provider transport/error behavior, settings validation, model-role config and fake parity. |
| JavaScript extension | Extension JS test suite via `npm run test:js` | Extension request/response, state and version behavior independent of Ollama. |

Exact filenames evolve; use the owning capability package guide and the test tree when a path has moved.

## Standard validation commands

From repository root:

```bash
ruff check .
python -m pytest -m "not real_llm" --cov --cov-report=term-missing --cov-report=xml
npm run test:js
pyright models rules_engine bootstrap operations
pyright
```

Run a focused deterministic test module before the full suite. The normal CI suite excludes live-provider tests.

### Live Ollama evaluation

```bash
python -m pytest -m real_llm -v -s
```

Run the relevant semantic, discourse, compound-intent, mechanics and proposal holdouts with explicit model/version/settings. Save allowlisted JSON metrics only. Never persist prompts, model completions, player messages, narration or hidden campaign content in evaluation artifacts.

### Manual SillyTavern acceptance

Use [the SillyTavern smoke-test checklist](../sillytavern-smoke-test.md) with a disposable campaign. Record backend SHA, extension SHA, model digest, Ollama version, configuration and result by case. Do not report this gate passed from pytest or an Ollama-only test.

## Product requirements are not implied test coverage

The v0.2 product requirements include future tests for multi-PJ control, NPC delegation, uncertainty thresholds/checkpoint continuation, first-party UI modes and accessible help, world compendium/inline entity references, per-field NPC visibility, fine-grained dice policies, custom rules modules, localization and full campaign import/export. Those contracts do not exist merely because this navigation page lists them. Add their tests alongside the first implementation PR for each backend contract, then add client acceptance tests when the UI arrives.

## Historical suite snapshots

[test-suite-navigation-2026-11-12.md](test-suite-navigation-2026-11-12.md) preserves the PR #205/#208-era test split and counts. [test-suite-audit-2026-11-11.md](test-suite-audit-2026-11-11.md) preserves the earlier structural audit. Neither is the current test inventory.
