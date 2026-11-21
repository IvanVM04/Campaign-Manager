# V3 acceptance gate and controlled ablations — 2026-11-22

## Purpose and trust boundary

PR #296 turns the v3 graph holdout into a predeclared acceptance experiment. It measures structural validity, exact graph match, precision/recall by dimension, false-positive fact candidates and repeat stability. It also identifies whether observed changes come from the v3 prompt, generation options or model selection.

The implementation is evaluation-only under `tests/`. The paired v2 call remains the current reference behavior and its rendered context is reused by the v3 shadow call for the same player input. Neither result is routed into mechanics, world proposals, narration, action selection, fact policy or persistence. Production remains on v2; a passing gate can only recommend manual review, never trigger a cutover.

The live acceptance runner is `tests/test_real_llm_player_turn_v3_acceptance.py`. It reuses the frozen 20-scenario graph-gold corpus from PR #293 and the graph scorer hardened by PRs #293–#295.

## Frozen acceptance contract

Contract identifier: `player-turn-v3-acceptance-2026-11-22-v1`.

The thresholds below are fixed before a live acceptance result is collected. They must not be lowered or the gold changed to make an existing run pass.

| Gate | Threshold | Denominator / interpretation |
|---|---:|---|
| Full holdout coverage | 20/20 scenarios | Each scenario must have a result in every declared repetition. A filtered run is diagnostic only. |
| Repetitions | At least 3 | Repetitions are sequential against one local Ollama daemon. |
| Critical structural validity | 100% | Valid strict v3 decoder results divided by all critical scenario/repetition runs. |
| Critical graph exact match | At least 80% | For each scenario, the majority outcome across repetitions must be an exact graph match; at least 16 of 20 scenarios. |
| Per-dimension precision | At least 90% | Independently for acts, events, links, facts, clarifications, source-act edges, discourse edges and clarification edges wherever predictions exist. |
| Per-dimension recall | At least 80% | Independently for each dimension with gold items. A strong aggregate cannot compensate for a weak dimension. |
| Critical false-positive fact candidates | 0 | Extra fact nodes in critical gold scenarios. This is a candidate-level safety gate, not evidence of an actual database write. |
| Repeat stability | At least 95% | Within each critical scenario, the modal exact/non-exact graph outcome divided by all repetitions. With three runs this requires all three outcomes to agree. |

A missing run, duplicate scenario/repetition key, invalid decoder result, low recall, extra critical fact or unstable critical outcome blocks eligibility. The report distinguishes diagnostic runs from full acceptance runs and includes the actual numerator/denominator for every gate.

These thresholds deliberately target the known failure mode in the previous v3 baseline: precision was high while recall was very low. The recall gate is separate from precision and exact-match gates. The 80% exact-graph gate is a minimum first promotion-review threshold on this 20-case holdout, not proof of production safety; the holdout still requires future expansion driven by audited failures.

## One-factor-at-a-time ablations

The runner creates a deterministic matrix:

| Variant | Changed factor | Kept constant |
|---|---|---|
| `baseline` | None | Full v3 prompt, server-default generation options, primary model |
| `without_coverage_procedure` | Prompt | Primary model and generation options; only the explicit clause-inventory/coverage procedure block is replaced |
| `fixed_sampling` | Generation options | Primary model and full prompt; `temperature=0`, `top_p=1`, `seed=1729` |
| `candidate_model` | Model (optional) | Full prompt and default generation options; compare a separately installed model |

The model candidate is opt-in and must differ from the primary model. Each variant still runs paired v2 then v3 calls for every selected input, repetition and context. Runs against the same Ollama daemon are sequential to avoid uncontrolled contention.

Reports contain the configured model, Ollama version, model digest where available, thinking mode, timeout, effective generation options, prompt/schema hashes, evidence-alignment version, commit SHA, per-scenario results and aggregate dimension metrics. The report does not contain player utterances, prompts, completions, campaign context, entity IDs or literal evidence spans.

## Run locally

The PowerShell runner provides a scoped entry point. It checks that the requested primary and optional candidate models are installed; it does not download Ollama models.

```powershell
# Full acceptance matrix; baseline + prompt + sampling ablations
.scriptsun-ollama-tests.ps1 -Evaluation v3-acceptance

# Optional model comparison (the model must already exist in Ollama)
$env:CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_CANDIDATE_MODEL = "candidate-model:tag"
.scriptsun-ollama-tests.ps1 -Evaluation v3-acceptance
```

Defaults: 3 repetitions, all 20 graph scenarios, and all available variants. The primary model comes from the configured intent role or `CAMPAIGN_MANAGER_REAL_LLM_MODEL`. With the three default variants, the full matrix makes 360 generation calls (20 scenarios × 3 repetitions × 2 paired v2/v3 calls × 3 variants); an optional candidate model adds 120. The run writes `ollama/reports/player-turn-v3-acceptance.json` under its unique quality-run directory.

Optional environment controls:

- `CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_REPETITIONS`: positive integer; values below 3 are diagnostic only.
- `CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_VARIANTS`: comma-separated variant IDs; must include `baseline`.
- `CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_CANDIDATE_MODEL`: optional distinct installed model.
- `CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_SCENARIO_ID`: one scenario ID for a quick diagnostic. Filtered runs cannot pass full acceptance.
- `CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_REPORT_PATH`: explicit report destination; the PowerShell runner sets a per-run path automatically.

For direct pytest execution:

```powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_V3_ACCEPTANCE_ENABLE = "1"
python -m pytest -m "real_llm and not nlp_pilot" tests/test_real_llm_player_turn_v3_acceptance.py -v -s
```

A quick diagnostic can set the scenario ID and one repetition, but must not be described as acceptance. Never run simultaneous acceptance variants against the same Ollama daemon.

## Decisions and next gates

A variant that passes all deterministic/report gates is marked `eligible_for_manual_review_only`. If no variant passes, the matrix reports `hold_v2`. The matrix may rank passing variants for review by critical graph exact match, macro dimension recall and latency; it does not select a model for production.

The live Ollama acceptance run is not part of deterministic CI and has not been executed by this PR. Manual SillyTavern acceptance, integrated action-selection/checkpoint tests, world-fact policy tests and false persistent mutation controls remain required in later integration milestones (#297–#300). No PR #296 result alone authorizes v3 rollout.
