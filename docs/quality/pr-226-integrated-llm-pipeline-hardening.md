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
- **PR:** [#226 — harden and validate the integrated LLM pipeline](https://github.com/IvanVM04/Campaign-Manager/pull/226); open, draft, not merged.
- **Last fully validated head before this live-probe configuration follow-up:** `349c3111b49ad4a3fbc4ae20867b8102c436ed07` (WP6 documentation/JSONL allowlist commit).
- **Completed packages:** WP0–WP6 implementation and deterministic validation complete. WP1 active-reference retrieval; WP2 authoritative v2 planner context and prompt compaction; WP3 integrated routing/failure/compound tests; WP4 Ollama safe usage telemetry, model/server metadata helpers and integrated live acceptance probe; WP5 strict-by-default legacy compatibility gate; WP6 documentation and JSONL allowlist synchronization.
- **Key implementation commits:**
  - WP1: `183be14676ef80c0bbbda516e3932ef6bb886359`, `3efec551867dad7f5285d932a76f08a757ce499d`, `6270853a7afc05214397525ae043454919682b1a`.
  - WP2: `708b33cea4320e54c538edbf860613b41685d9e4`, `c6a863a545ff8d51dcd6e2a02468a23cb26120a4`, `00936f3de281405d743f813bcb7159dbb9433f3a`.
  - WP3: `4a326a38598a135d88ed339707330d075ed3abe1`, `4f1d183aef61678c37fb18d04474e885af00a4f1`.
  - Prompt compaction: `4d45880db0ac9d6fc24a8b82f822f692b735a5c1`, `51aa35c7938a043b715bfc6f777bf17a7663e067`.
  - WP4: `183f1108b3eb958470d735e4da981a99c69859a6`, `b5b165e4848be7c1b778ef7cc7420de31ba7c3a6`, `4936e30cc7d3e68853150058a16df5e4ea1812e9`.
  - WP5: `45ed0849dd612b21e2cd9ff04b68fbf54bb5c671`; strict-by-default and fixture migration: `40902a6dbf32921a2b795e791e198f4dab4f25de`.
- **Current implementation state:** production runtime has separate intent, mechanics and extraction providers; the same immutable interpretation passes through deterministic resolution to mechanics and planner; planner avoids duplicate transcript/discourse and does not advance future conditional steps. Mechanics uses only active-step resolved references. Legacy combined APIs remain deprecated compatibility shims and the turn-service fallback is disabled by default and in production. Ollama telemetry collects role/model, UTF-8 prompt bytes, token counts, nanosecond/millisecond timings and completion metadata without logging prompts or completions. JSONL now allowlists the bounded diagnostic fields. Documentation is synchronized.
- **Latest deterministic validation:** workflow [`43633474841`](https://github.com/IvanVM04/Campaign-Manager/actions/runs/43633474841) passed on head `349c3111b49ad4a3fbc4ae20867b8102c436ed07`: **1,826 passed, 17 deselected**, combined coverage **85.13%**. Ruff, repository/scoped Pyright, JavaScript tests and CodeQL [`43633474838`](https://github.com/IvanVM04/Campaign-Manager/actions/runs/43633474838) passed. The final live-probe environment override and checkpoint hash correction below require a fresh CI run.
- **Live Ollama validation:** not run here. Run `python -m pytest tests/test_real_llm.py -m real_llm -k integrated_pipeline -v -s`, then the remaining real-LLM corpus using the exact local model tag/settings. Record the generated JUnit/properties and usage metrics; do not mark pass from code presence alone.
- **SillyTavern validation:** not run for PR #226. Use [the manual smoke-test checklist](../sillytavern-smoke-test.md) against recorded backend and extension revisions; cover multi-chat isolation, clarification rounds, duplicate delivery, manual dice and restart recovery.
- **Open blockers:** validate the live-probe environment override follow-up in deterministic CI. External consumers of the deprecated combined response may still exist; keep the shim until their migration is verified. Most importantly, integrated local Ollama quality and the real SillyTavern lifecycle remain outstanding acceptance gates.
- **Next exact action:** inspect CI for the live-probe configuration follow-up. If green, execute the integrated Ollama probe using `CAMPAIGN_MANAGER_REAL_LLM_MODEL`, `CAMPAIGN_MANAGER_REAL_LLM_BASE_URL` and `CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT`, then run the remaining live corpora and manual SillyTavern checklist. Keep PR #226 open in draft until those environment-dependent results are recorded.

### How to resume

When returning to this work, first read this checkpoint and inspect the live branch/PR head. Continue from **Next exact action**; do not redo completed packages or assume an earlier CI result covers a newer commit. After every code/documentation package:
1. commit the code/tests/docs together;
2. update this checkpoint with commit SHA and validation result;
3. re-read the changed code from the branch;
4. verify CI state before reporting success.

If the user says “continúa PR #226”, resume this branch and this checkpoint. Do not create another branch or PR unless this one is confirmed unavailable.
