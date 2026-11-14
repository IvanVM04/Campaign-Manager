# PR #226 — Integrated LLM pipeline hardening

**Status:** PR #226 merged into `main` on 2026-11-14 at 20:00:17, merge commit `61725a03346d2ebfcf0ce6b2aacf92c0b6789b28`. Deterministic CI passed on final PR head `92d2861f183aecb3fe956a1b9da4834e052a8550`; local Ollama and SillyTavern acceptance remain pending.  
**Base:** `main` at `e59bc47e85edb8efa4d02e5eb9990de0438d3486` (PR #225 merge)  
**Priority:** P0 — validate the modular pipeline before adding more semantic capabilities  
**Owner of next action:** continue from the checkpoint below; do not restart the design or create a second branch.

## 1. Objective

Harden and validate the production path introduced by PR #225:

`player evidence → IntentInterpreter → deterministic validation/reference resolution → conditional MechanicsAdjudicator → World Consequence Planner → deterministic domain validation/commit → narration`

The target is not to add more agents or split one semantic representation into multiple LLM calls. Keep one authoritative `PlayerIntentAnalysis v2` and improve the boundaries, context selection, integration tests, diagnostics and migration from the former combined adjudicator.

A green deterministic suite is necessary but is not evidence of model quality. Live Ollama and manual SillyTavern acceptance remain separate gates.

## 2. Decisions carried forward

1. **One semantic interpretation.** Actions, arguments, relations, discourse, modality, polarity and attribution remain one coherent Intent Interpreter response.
2. **Mechanics is conditional and narrow.** It receives the validated active step, resolved canonical references, relevant visible facts and active-character mechanics; it returns only `MechanicsDecision`.
3. **Planner is a consequence translator.** It consumes the same interpretation, trusted references and confirmed mechanics outcome. It must not become a second intent interpreter.
4. **Deterministic code remains authoritative.** Resolvers own identity and visibility; the rules engine owns rolls/results; domain services own validation and persistence.
5. **No new multi-agent framework, vector database, provider retry policy or database migration** unless this PR produces evidence that it is necessary.
6. **Evidence must not be silently clipped.** Only ranked optional context may be compacted or omitted, and its omission should be observable.

## 3. Work packages and acceptance criteria

### WP0 — Branch, specification and resumability
- [x] Create this branch from the merged PR #225 commit.
- [x] Add this implementation specification with a durable checkpoint.
- [x] Update linked architecture/quality docs as work lands.
- [x] Open a draft PR after the first functional slice is committed.

### WP1 — Mechanics context retrieval hardening
**Problem observed:** `MechanicsAdjudicator.adjudicate_analysis()` currently searches using only `step.source_excerpt`, even when deterministic resolution has supplied canonical entity/world-record names. A pronoun or ellipsis may resolve correctly but still retrieve too little descriptive/mechanical context.

**Planned change:**
- Build bounded supplemental retrieval queries from the active step's *already filtered* resolved references.
- Include the canonical entity/world-record name and the literal mention; preserve the step excerpt as the primary query.
- Do not query from unrelated references, prior-turn dumps or model-supplied canonical IDs.
- Keep visibility and active-character perspective in the existing ContextBuilder.
- Add deterministic tests proving the supplemental query set contains active canonical names and excludes unrelated references.

**Acceptance:**
- A reference resolved from a prior turn can retrieve its canonical record description for adjudication.
- References unrelated to the active step are not included.
- The original player evidence and all current trust boundaries remain unchanged.
- Provider prompt stays within the mechanics byte budget or fails with a useful per-section diagnostic.

### WP2 — Planner context specialization
**Problem observed:** the proposal prompt includes the shared analysis, raw player utterance, recent history and discourse index. Some duplication is useful as evidence, but it creates an opportunity for the planner to re-interpret intent and consumes budget.

**Planned change:**
- Classify each proposal section as required evidence, trusted application result or optional context.
- Preserve shared analysis, evidence needed to ground operations, trusted references, selected world state, operation allowlist and confirmed mechanics.
- Avoid duplicating history/discourse when it adds no distinct evidence already represented by the shared analysis and resolved references.
- Keep optional evidence available only where it materially helps identify a world fact; omission must not erase active-step evidence.
- Add prompt-contract tests for required/forbidden sections and compact-budget cases.

**Acceptance:**
- Planner instructions explicitly prioritize the validated analysis.
- No raw history is treated as authority or a replacement interpretation.
- No change to operation allowlist, typed references, parser trust gate or domain authority.
- Prompt budget diagnostics show section sizes and compaction/omission decisions.

### WP3 — Integrated deterministic pipeline contract
- [x] Exercise the actual orchestrator and assert stage call order and exact analysis-object handoff.
- [x] Cover a routine/completed observation (no mechanics call), a positive uncertain attempt (mechanics call), ambiguous target (stop before mechanics/planner), failed attempt (confirmed failure reaches the planner), compound action (future conditional step remains unexecuted after a failed prerequisite), and question/plan/negation (no mechanics or unsupported mutation).
- [x] Assert mechanics receives the same selected world projection and only active-step resolved references.
- [x] Assert proposal receives the same immutable analysis and only trusted reference results.
- **Validation:** run `43626291437` passed with 1,818 tests, 16 deselected and 85.16% combined coverage.

### WP4 — Live Ollama acceptance and model telemetry
- [x] Keep live tests opt-in under `-m real_llm`; deterministic CI must not require Ollama.
- [x] Add an integrated probe that obtains intent from the live interpreter, passes it through the production resolution path, then measures mechanics/planner calls and operations.
- [x] Pending-correction live coverage already uses `IntentInterpreter.understand_pending()`; it does not require the former combined mechanics/correction response.
- [x] Ollama adapter telemetry records role/model, UTF-8 prompt bytes, response model, prompt/evaluation token counts and timing metadata when supplied by the server; a safe callback exposes per-call records to live probes.
- [x] Add optional Ollama server-version and configured model-digest lookup, plus stage result-family logs.
- [x] Never log full prompts, completions, secrets or campaign data.
- **Live execution:** not run in this environment; the integrated fixture remains opt-in and must be run against the configured local Ollama model.

### WP5 — Retire the former combined path
- [x] Inventory production and test consumers of `MechanicsAdjudicator.understand()` and `understand_pending()`.
- [x] Keep the modular `IntentInterpreter` + `adjudicate_analysis()` path as the only application-runtime path.
- [x] Gate the old combined service fallback behind `allow_legacy_combined_understanding`; the production composition root explicitly disables it.
- [x] Document `understand()`, `understand_pending()` and `adjudicate()` as deprecated compatibility shims; retain combined prompt/schema only for old external integrations and compatibility-contract tests.
- [x] Add a composition-root regression test and a fail-closed test for callers that disable the shim.
- **Inventory:** the only production references are the two fallback branches in `TurnResolutionService`, reachable only for callers that omit `IntentInterpreter` and explicitly enable compatibility. The runtime composition root injects distinct role providers and sets compatibility to `False`. Deterministic compatibility fixtures remain opt-in; live model probes use the role-specific path.
- **Follow-up:** remove the compatibility prompt/schema only when downstream integrations no longer depend on the combined response contract.

### WP6 — Documentation and handoff
- [x] Update `services/turns/README.md`, `services/providers/README.md`, and the modular pipeline decision record.
- [x] Synchronize the prompt-evaluation guide, current AI-understanding roadmap, observability policy and documentation hub with the role-specific runtime path.
- [x] Extend the JSONL allowlist to retain safe Ollama usage and stage-result metadata; add an allowlist regression test so token/timing fields are actually persisted.
- [x] Keep this file's checkpoint accurate after every meaningful implementation block.
- [x] Record completed commits, deterministic CI results, unresolved environment-dependent acceptance gates and the exact next action.

## 4. Explicit non-goals

- No extra LLM calls to separately extract actions, relations, roles or attribution.
- No autonomous mutation, planner authority over dice/results, or model-selected canonical IDs.
- No broad semantic feature expansion (advanced ellipsis, temporal graphs, causal graphs, etc.) until the integrated pipeline is measured.
- No claim that deterministic CI proves model quality or SillyTavern compatibility.

## 5. Validation commands

Deterministic suite:
```bash
python -m pytest -m "not real_llm" --cov --cov-report=term-missing
```

Focused pipeline tests:
```bash
python -m pytest tests/test_modular_language_pipeline.py tests/test_mechanics_adjudicator.py tests/test_turn_resolution_service.py -q
```

Live Ollama suite (run only when the configured local Ollama model is available):
```bash
python -m pytest -m real_llm -v -s
```

Do not mark a live gate as passed based on deterministic CI. Record model/tag, Ollama version, environment/settings, test IDs, failures, latency and metrics.

## 6. Durable continuation checkpoint

This section is the source of truth for resuming work after an interruption. Update it in the same commit as the work it describes.

### Current checkpoint

- **Branch:** `feat/226-integrated-llm-pipeline-hardening`
- **Base commit:** `e59bc47e85edb8efa4d02e5eb9990de0438d3486`
- **Final merged PR head:** `92d2861f183aecb3fe956a1b9da4834e052a8550`
- **PR:** [#226 — harden and validate the integrated LLM pipeline](https://github.com/IvanVM04/Campaign-Manager/pull/226); merged and closed. Merge commit: `61725a03346d2ebfcf0ce6b2aacf92c0b6789b28`.
- **Branch comparison at audit time:** 26 commits ahead of `main`, 0 behind.
- **Completed packages:** WP0–WP6 complete. WP1 active-reference mechanics retrieval; WP2 authoritative v2 planner context and budget compaction; WP3 integrated deterministic routing/failure/compound-action tests; WP4 role-aware Ollama telemetry and integrated live probe; WP5 strict-by-default legacy compatibility gate; WP6 service/architecture/evaluation/roadmap/observability documentation and safe JSONL telemetry allowlist. The live probe follow-up also honors common endpoint and timeout overrides and records each provider role's model digest.
- **Key implementation commits:** WP1 `183be14676ef80c0bbbda516e3932ef6bb886359`, `3efec551867dad7f5285d932a76f08a757ce499d`, `6270853a7afc05214397525ae043454919682b1a`; WP2 `708b33cea4320e54c538edbf860613b41685d9e4`, `c6a863a545ff8d51dcd6e2a02468a23cb26120a4`, `00936f3de281405d743f813bcb7159dbb9433f3a`; WP3 `4a326a38598a135d88ed339707330d075ed3abe1`, `4f1d183aef61678c37fb18d04474e885af00a4f1`; prompt compaction `4d45880db0ac9d6fc24a8b82f822f692b735a5c1`, `51aa35c7938a043b715bfc6f777bf17a7663e067`; WP4 telemetry/probe `183f1108b3eb958470d735e4da981a99c69859a6`, `b5b165e4848be7c1b778ef7cc7420de31ba7c3a6`, `4936e30cc7d3e68853150058a16df5e4ea1812e9`; WP5 `45ed0849dd612b21e2cd9ff04b68fbf54bb5c671`, strict compatibility/fixture migration `40902a6dbf32921a2b795e791e198f4dab4f25de`; WP6 `349c3111b49ad4a3fbc4ae20867b8102c436ed07`; live-probe override follow-up `b0bb31d64d610c55dbb9a9da53e7d5e5db004c22`.
- **Final deterministic validation on merged head `92d2861...`:** Tests workflow [`43634512713`](https://github.com/IvanVM04/Campaign-Manager/actions/runs/43634512713) passed: **1,826 passed, 17 deselected, 85.13% combined coverage** (85.0% gate). Ruff, repository-wide Pyright, scoped Pyright and JavaScript checks passed. CodeQL [`43634512738`](https://github.com/IvanVM04/Campaign-Manager/actions/runs/43634512738) passed for Python and JavaScript/TypeScript.
- **Current implementation state:** production runtime composes distinct intent, mechanics and extraction roles. A single immutable semantic analysis passes through deterministic reference resolution to mechanics and the planner. The mechanics role only judges the active validated step; the planner only proposes typed consequences; domain services retain validation and persistence authority. Legacy combined methods remain deprecated compatibility shims, and the application runtime disables their fallback.
- **Live Ollama validation:** not run for PR #226. First run:
  ```bash
  python -m pytest tests/test_real_llm.py -m real_llm -k integrated_pipeline -v -s
  ```
  The probe supports `CAMPAIGN_MANAGER_REAL_LLM_MODEL`, `CAMPAIGN_MANAGER_REAL_LLM_BASE_URL` and `CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT`; record the resolved model per role, model digests, Ollama version, timeout/settings, calls, prompt bytes, input/output tokens, latency and operation output.
- **SillyTavern validation:** not run for PR #226. Use [the manual smoke-test checklist](../sillytavern-smoke-test.md) against recorded backend and extension revisions; cover multi-chat isolation, clarification rounds, duplicate delivery, manual dice and restart/replay recovery.
- **Remaining acceptance:** no deterministic CI blocker remained at merge. Local Ollama quality and manual SillyTavern lifecycle acceptance are still unexecuted; keep the deprecated combined path until external compatibility consumers are identified and migrated.
- **Follow-up after merge:** run the integrated local Ollama probe above, inspect the per-role trace and semantic result, then run the relevant live corpora. If clean, complete the SillyTavern smoke checklist. These are post-merge environment acceptance gates, not reasons to rewrite the merged implementation without evidence.

### How to resume

When returning to this work, first read this checkpoint and inspect the live branch/PR head. Continue from **Next exact action**; do not redo completed packages or assume an earlier CI result covers a newer commit. After every code/documentation package:
1. commit the code/tests/docs together;
2. update this checkpoint with commit SHA and validation result;
3. re-read the changed code from the branch;
4. verify CI state before reporting success.

If the user says “continúa PR #226”, resume this branch and this checkpoint. Do not create another branch or PR unless this one is confirmed unavailable.


## 7. Architecture audit and delivery estimate — 2026-11-14

### Architectural verdict

The responsibility separation is sound for this tranche. The goal is to divide *responsibilities*, not fragment one meaning representation across separate model calls:

1. **IntentInterpreter:** one coherent, versioned `PlayerIntentAnalysis v2` describes steps, action frames, semantic roles, relations, modality, polarity and attribution. The typed analysis is checked against player evidence.
2. **Deterministic resolution:** canonical identity, scope, visibility and ambiguity are owned by deterministic resolvers. Ambiguity returns a clarification before mechanics.
3. **MechanicsAdjudicator:** receives the validated active step, active-step resolved references, visible world facts and character mechanics; returns only `MechanicsDecision`. Canonical names/literal mentions are supplemental retrieval queries only after deterministic resolution.
4. **World Consequence Planner:** receives the same semantic analysis, trusted resolved references and confirmed mechanics outcome. It returns untrusted typed proposals; it is not a second interpreter or rules engine.
5. **Domain services:** validate and apply proposals; rules code owns checks/results; narration follows committed consequences.

The production composition root creates distinct role providers and explicitly disables `allow_legacy_combined_understanding`. The combined legacy APIs remain only as opt-in compatibility shims. That is the correct migration posture while callers are being verified.

### Non-blocking design debt

- `TurnResolutionService` is still a large application orchestrator. Do not rewrite it during this PR. After live behavior is measured, extract only independently testable lifecycle collaborators (for example, context/reference preparation and mechanics execution), preserving its orchestration contract.
- `MechanicsAdjudicator` still contains deprecated combined prompts/methods. Remove or move them to a dedicated compatibility adapter only after external consumers migrate and compatibility tests prove it.
- Planner prompt compaction uses several ranked fallbacks and replacement of rendered string sections. It is guarded by prompt-contract tests, but a future improvement should model prompt sections as typed required/optional units with explicit priority and render once after compaction.
- `estimate_tokens()` counts UTF-8 bytes, not model tokens. Documentation now clarifies the byte budget; later rename old `*_MAX_TOKENS` aliases after migration to avoid operational confusion.
- Combined coverage is **85.13%**, only 0.13 percentage points above the enforced 85.0% floor. Target 86–87% for healthy headroom.

### Progress

These percentages measure engineering delivery, not the semantic accuracy of the local model:

| Area | Progress | Evidence / remaining work |
|---|---:|---|
| Production responsibility split | 90% | Role boundaries and strict production composition are implemented; compatibility shims remain. |
| Deterministic routing and trust boundaries | 100% of PR scope | 1,826 passed; 17 opt-in real-model tests excluded from deterministic CI. |
| Telemetry and live-probe implementation | 100% of PR scope | Per-role usage, model metadata, safe JSONL allowlist and integrated probe exist. |
| Live Ollama evidence for this PR | 0% executed | Run probe/corpora with the configured local model. |
| SillyTavern acceptance for this PR | 0% executed | Manual lifecycle checklist remains. |
| **Overall PR closure** | **80–85%** | Implementation and deterministic checks are done; environment-dependent acceptance is outstanding. |

### Remaining effort

| Task | Estimated active effort |
|---|---:|
| Integrated Ollama probe and telemetry/semantic review | 1–2 h |
| Wider targeted live corpus and results capture | 0.5–1.5 h |
| SillyTavern smoke test and evidence capture | 1–2 h |
| Prompt/routing fixes and repeat validation, if needed | 0–3 h additional |

If the live checks are clean, expect **2.5–5 active hours** to close the PR. Allow **5–8 hours** if the configured model exposes issues. Local inference latency depends on hardware and is not included as active work.

### Recommended next tranche

Make the next quality PR evaluation-led, not another architecture split. Version a golden corpus for ellipsis and distant references, topic shifts, grammatical agreement, NPC speaker attribution, quoted/reported speech, negation, conditional/compound actions and multi-turn corrections. Define invariants and separate deterministic routing checks from live-model quality scores. Use per-stage results (intent, resolution, mechanics, proposal) to locate regressions instead of one aggregate success percentage.
