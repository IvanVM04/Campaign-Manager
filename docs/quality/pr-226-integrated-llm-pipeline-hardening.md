# PR #226 — Integrated LLM pipeline hardening

**Status:** in progress on `feat/226-integrated-llm-pipeline-hardening`  
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
- [ ] Update linked architecture/quality docs as work lands.
- [ ] Open a draft PR after the first functional slice is committed.

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
- Update `services/turns/README.md`, `services/llm_world/README.md`, and the modular pipeline decision record.
- Keep this file's checkpoint accurate after every meaningful implementation block.
- Record completed commits, test commands/results, unresolved issues, and the exact next action.

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
- **PR:** [#226 — harden and validate the integrated LLM pipeline](https://github.com/IvanVM04/Campaign-Manager/pull/226); open, not merged, draft.
- **Current head:** pending strict-by-default compatibility gate and migrated legacy fixtures.
- **Completed packages:** WP0 complete; WP1 mechanics reference retrieval implemented; WP2 planner context specialization and v2 prompt-budget regression fix implemented; WP3 deterministic integrated routing complete; WP4 Ollama usage telemetry and integrated live probe implemented (live run pending); WP5 legacy combined fallback gated off in production runtime, documented as compatibility-only, with regression tests.
- **Key implementation commits:**
  - WP1: `183be14676ef80c0bbbda516e3932ef6bb886359`, `3efec551867dad7f5285d932a76f08a757ce499d`, `6270853a7afc05214397525ae043454919682b1a`.
  - WP2: `708b33cea4320e54c538edbf860613b41685d9e4`, `c6a863a545ff8d51dcd6e2a02468a23cb26120a4`, `00936f3de281405d743f813bcb7159dbb9433f3a`.
  - WP3: `4a326a38598a135d88ed339707330d075ed3abe1`, `4f1d183aef61678c37fb18d04474e885af00a4f1`.
  - WP2 compaction fix: `4d45880db0ac9d6fc24a8b82f822f692b735a5c1`, `51aa35c7938a043b715bfc6f777bf17a7663e067`.
  - WP4 telemetry/live probe: `183f1108b3eb958470d735e4da981a99c69859a6`; linter follow-up `b5b165e4848be7c1b778ef7cc7420de31ba7c3a6`; partial-result telemetry compatibility fix `4936e30cc7d3e68853150058a16df5e4ea1812e9`.
- **Current implementation state:** mechanics retrieves active-step canonical and literal references; v2 planner uses one shared analysis; integrated deterministic tests verify routing, mechanics failure propagation and blocked conditional progression. Ollama usage metadata is captured without logging prompt/completion content. The role-specific production runtime disables the former combined contract; an explicit compatibility switch remains for older callers and tests only.
- **Deterministic validation:** WP4 head run [`43629723969`](https://github.com/IvanVM04/Campaign-Manager/actions/runs/43629723969) passed: **1,823 passed, 17 deselected**, **85.14%** combined coverage. Ruff, both Pyright jobs, JavaScript tests and CodeQL [`43629723957`](https://github.com/IvanVM04/Campaign-Manager/actions/runs/43629723957) passed.
- **Live Ollama validation:** not run here. Opt-in integrated test: `test_real_ollama_integrated_pipeline_does_not_advance_failed_compound_action`.
- **SillyTavern validation:** not run for PR #226.
- **CI history:** WP5 first run `43630505741` had 1 failing compatibility test because a reloaded legacy SillyTavern test did not opt back in after constructing a fresh runtime; 1,824 passed, 17 deselected and coverage was 85.10%. The current patch changes compatibility to opt-in by default and migrates that reloaded fixture plus the direct combined mechanics integration helper. Recheck CI on the new head.
- **Open blockers:** validate strict-by-default WP5 in deterministic CI. Then WP6 final documentation/audit remains; live Ollama and first SillyTavern checks remain separate acceptance gates.
- **Next exact action:** inspect CI for the strict-by-default WP5 commit. If green, complete WP6 docs/audit and hand off the exact live Ollama command and remaining SillyTavern checklist. Do not remove the legacy combined schema until external consumers migrate and that migration is tested.

### How to resume

When returning to this work, first read this checkpoint and inspect the live branch/PR head. Continue from **Next exact action**; do not redo completed packages or assume an earlier CI result covers a newer commit. After every code/documentation package:
1. commit the code/tests/docs together;
2. update this checkpoint with commit SHA and validation result;
3. re-read the changed code from the branch;
4. verify CI state before reporting success.

If the user says “continúa PR #226”, resume this branch and this checkpoint. Do not create another branch or PR unless this one is confirmed unavailable.
