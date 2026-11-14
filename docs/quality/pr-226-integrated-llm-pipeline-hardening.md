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
- Exercise the actual orchestrator and assert stage call order and exact analysis-object handoff.
- Cover a routine/completed observation (no mechanics call), a positive uncertain attempt (mechanics call), ambiguous target (stop before mechanics/planner), failed attempt (no false success proposal), compound action (do not advance after a failed prerequisite), question/plan/negation (no mechanics or unsupported mutation).
- Assert mechanics receives the same selected world projection and only active-step resolved references.
- Assert proposal receives the same immutable analysis and only trusted reference results.

### WP4 — Live Ollama acceptance and model telemetry
- Keep live tests opt-in under `-m real_llm`; deterministic CI must not require Ollama.
- Add a true integrated probe that obtains intent from the live interpreter, passes it through the production resolution path, then measures mechanics/planner calls and operations.
- Migrate the pending-correction live probe to `IntentInterpreter.understand_pending()`; remove dependence on the old combined correction contract.
- Record pinned model name/tag (and digest when obtainable), Ollama version when obtainable, role, prompt bytes, actual prompt/evaluation token counts when present, stage latency, provider calls, result family and error type.
- Do not log full prompts, full completions, secrets or full campaign data.
- Compare same fixtures/model/settings before and after; report intent accuracy, frame/role accuracy, operation quality, critical false persistent changes, latency and call count separately.

**Acceptance:**
- No critical false persistent changes.
- Critical semantic/operation controls pass on the pinned local model.
- Model, environment, settings and results are reproducible.
- Provider/decoder/budget errors count as failures, not silently skipped cases.

### WP5 — Retire the former combined path
- Inventory all production/test consumers of `MechanicsAdjudicator.understand()` and `understand_pending()`.
- Migrate live and deterministic integration fixtures to `IntentInterpreter` + `adjudicate_analysis()`.
- Keep only a deliberately documented compatibility shim if an external consumer still exists; do not use it from production runtime.
- Remove duplicate combined prompt/schema once the migration is complete and test its absence from the production composition root.

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
- **PR:** not opened yet; create as draft after WP1's first functional commit.
- **Last completed package:** WP1 implementation and deterministic regression fixture are committed; CI is currently validating the PR head.
- **Last completed commit:** `33470c1359e4c4e2c25da8f69a687f6e5c4e0244` (documentation follow-up; WP1 runtime/test commits are `183be14676ef80c0bbbda516e3932ef6bb886359`, `3efec551867dad7f5285d932a76f08a757ce499d`, and `6270853a7afc05214397525ae043454919682b1a`).
- **Current implementation state:** `MechanicsAdjudicator.adjudicate_analysis()` derives at most 32 deduplicated supplemental queries from canonical names and literal mentions belonging only to active-step-filtered resolved references. It sends them to the existing visibility-aware `ContextBuilder.build()` alongside the active step's exact source excerpt. Prompt diagnostics record the query-byte footprint without logging query contents.
- **Deterministic validation:** PR #226 CI run `43622216494` is in progress; focused test and static results not yet confirmed.
- **Live Ollama validation:** not run for PR #226.
- **SillyTavern validation:** not run for PR #226.
- **Open blockers:** none known; await the first PR #226 CI result and fix any regression before proceeding.
- **Next exact action:** inspect Tests and CodeQL run `43622216494` / `43622216493`. If green, proceed to WP2 by classifying proposal prompt sections, then add tests showing the planner keeps the shared analysis and required evidence while omitting redundant non-authoritative history/discourse only under the explicitly selected policy. If CI fails, fix that before WP2. Do not change the one-analysis architecture or remove required current-player evidence.

### How to resume

When returning to this work, first read this checkpoint and inspect the live branch/PR head. Continue from **Next exact action**; do not redo completed packages or assume an earlier CI result covers a newer commit. After every code/documentation package:
1. commit the code/tests/docs together;
2. update this checkpoint with commit SHA and validation result;
3. re-read the changed code from the branch;
4. verify CI state before reporting success.

If the user says “continúa PR #226”, resume this branch and this checkpoint. Do not create another branch or PR unless this one is confirmed unavailable.
