# V3 acceptance, rollout readiness and SillyTavern checklist — 2026-11-23

**Roadmap:** PR #300 release gate; PR #301 begins the P0 durable integration in draft.  
**Current decision:** `HOLD V2`.  
**Production authority:** v2.  
**Ollama acceptance:** NOT RUN by this PR.  
**Manual SillyTavern acceptance:** NOT RUN by this PR.

This document is the operational acceptance plan for the V3 migration. It deliberately separates semantic model quality, durable runtime integration and real client behavior. Passing one gate never substitutes for another.

## 1. Current source-verified implementation boundary

PR #299 is merged in `main` at `556feeb17ff227448bc159aa5c823f7441bb5c03` (2026-11-23). Its deterministic CI completed with 2,635 passed, 26 deselected and 85.01% combined coverage; Ruff, both Pyright checks, JavaScript, PowerShell and CodeQL also passed.

PR #299 provides the compound-action state-machine core, one-node-at-a-time orchestration, the V3 planning adapter, staged progress serialization/recovery primitives and checkpoint/progress CAS persistence. Those components have deterministic unit and contract coverage.

**PR #302 (main-targeting draft, superseding #301) wires the first bounded V3 execution path into `DurableTurnExecutionService`:** with both shadow and action-execution flags explicitly enabled, automatic-dice graphs whose initial references are resolved are planned action-by-action through `V3ActionPlanningAdapter` and `V3CompoundActionOrchestrator`. A dependent action receives an isolated virtual projection with staged predecessor world operations applied. Checkpoint transitions and staged progress use the existing planning lease, campaign revision and checkpoint CAS; resolved action plans are aggregated for one prepared commit. Per-action mechanics outcomes are retained for narration rather than collapsing all actions to the final mechanics result. Staged progress can be restored after a crash without re-running the action proposal provider.

This is a partial integration, not a completed acceptance gate. Manual-dice turns and graphs that initially require clarification remain on V2. If a V3 action unexpectedly asks for clarification, execution fails closed and keeps its checkpoint/progress; it does not commit a partial plan. The current virtual projection does not support staged character operations and fails closed if one appears. PR #302 also adds a deterministic test through the native durable service, prepared commit and narration boundary, but not the complete Gate B matrix. The previous draft PR #301 is superseded and should be closed after #302 validates. Same-node manual-roll/clarification continuations are planned for PR #303. Full durable service/transaction, lease-expiry, stale-revision, negative-control and historical replay evidence remains for PR #304.

The following remain incomplete or unaccepted:

- Same-node durable continuation for V3 manual rolls and clarification answers.
- Virtual projection of staged character operations (currently rejected fail-closed).
- Complete deterministic end-to-end proof for dialogue, no-roll actions, rolled actions, invalid proposals and failures through the actual durable service and repository.
- Lease expiry/replacement, crash windows, stale revision, idempotent replay and rollback/zero-write negative controls.
- Historical V1/V2 durable-record replay through the real service.
- A complete manual SillyTavern conversation using the integrated compound-action runtime.

The execution flag now exists but is default-off. It must not be enabled for live/production use until the remaining P0 continuations and integration evidence pass. The flags are:

| Setting | Default | Actual authority |
|---|---:|---|
| `CAMPAIGN_MANAGER_PLAYER_TURN_V3_ACTION_SHADOW_ENABLED` | `false` | Builds the V3 preview/checkpoint. It does not execute the action graph. |
| `CAMPAIGN_MANAGER_PLAYER_TURN_V3_WORLD_FACTS_ENABLED` | `false` | Enables independently evaluated, receipt-bound fact operations through the existing prepared commit. Requires action-shadow to be enabled. |
| `CAMPAIGN_MANAGER_PLAYER_TURN_V3_ACTION_EXECUTION_ENABLED` | `false` | Runs only the partial automatic/initially-resolved compound graph path implemented by PR #302. Requires action-shadow to be enabled. Keep disabled until PRs #301–#304 and the release gate are accepted. |

Even when the new execution flag is enabled for controlled development, the implementation is partial; V2 remains the production authority and release decision.

## 2. Gate A — frozen V3 semantic acceptance with Ollama

The live runner is `tests/test_real_llm_player_turn_v3_acceptance.py`. It uses the frozen graph-gold holdout from PR #293 and the graph scorer hardened by PRs #293–#295. It runs paired v2/v3 calls and one-factor ablations. It is an evaluation harness only: it does not send V3 output to mechanics, proposals, action execution, persistence or narration.

### Required run

Use a clean local checkout and the configured Ollama daemon. The evaluation script checks model availability; it does not download Ollama models.

From PowerShell:

```powershell
.\scripts\run-ollama-tests.ps1 -Evaluation v3-acceptance -SkipNlpPilot -SkipNlpModelDownload
```

The runner selects the acceptance test, enables it for that process, scopes the report to a unique quality-run directory and writes:

`artifacts/quality-runs/<run-id>/ollama/reports/player-turn-v3-acceptance.json`

The default full run covers 20 scenarios, 3 repetitions and the three built-in variants (baseline, without coverage procedure, fixed sampling): 360 provider calls. An optional, separately installed candidate model adds another 120 calls. Do not run acceptance variants concurrently against the same Ollama daemon. A filtered scenario or fewer than three repetitions is diagnostic only and cannot pass the full acceptance gate.

The report manifest must identify the exact commit, acceptance contract, corpus fingerprint, configured model, Ollama/runtime details available from the provider, variant, repetition and call counts. Shared reports must remain content-free: no player utterances, prompts, completions, campaign context, literal spans or canonical entity IDs.

### Frozen thresholds — do not tune after observing results

| Gate | Required |
|---|---:|
| Full held-out graph corpus | 20/20 scenarios in every repetition |
| Critical repetitions | At least 3, sequential |
| Critical structural validity | 100% |
| Critical graph exact match | At least 80% (majority exact in at least 16/20 scenarios) |
| Precision per semantic dimension | At least 90% |
| Recall per semantic dimension | At least 80% |
| Critical false-positive fact candidates | 0 |
| Repeat stability | At least 95% |

A high precision score cannot compensate for weak recall. A result that passes this experiment is only `eligible_for_manual_review_only`; it is not evidence of durable action execution, successful database writes, or SillyTavern acceptance.

**Result for PR #300:** NOT RUN. No new Ollama acceptance result is asserted by this PR.

## 3. Gate B — deterministic durable-runtime integration

Before attempting V3 compound execution in a real SillyTavern chat, every check below must have a passing deterministic integration test on the candidate commit. The PR #299 orchestration unit tests alone do not satisfy this gate.

| Required check | Current status | Evidence required |
|---|---|---|
| Compound orchestrator wired to `DurableTurnExecutionService` | PARTIAL — PR #301 draft | Wiring exists; still needs end-to-end durable service/repository evidence on the candidate SHA |
| Dependent action sees virtual projection of prior staged operations | PARTIAL — PR #301 draft | World-operation projection exists; needs dependency test through the durable service; character-operation projection fails closed |
| Manual roll resumes the same action checkpoint | BLOCKED | Durable submission/recovery test with stable event and execution identity |
| Clarification resumes the same action checkpoint | BLOCKED | Durable clarification flow that preserves the stored graph and unrelated nodes |
| Action operations and independent fact operations share one aggregate proposal and one atomic commit | BLOCKED | Repository/commit integration test with rollback assertion |
| Every transition remains lease-fenced and CAS-protected | BLOCKED | Expired lease, lease replacement and stale checkpoint tests |
| Crash recovery is idempotent after mechanics execution | BLOCKED | Crash injection between execution, staging and outcome persistence; same execution key on replay |
| Stale campaign revision rejects without writes | BLOCKED | Revision conflict integration test asserting no partial operations |
| Critical negative controls produce zero unauthorized writes | BLOCKED | Before/after state comparison for quote, report, rumor, hypothesis, negation, failed attempt and ambiguous target |
| Historical V1/V2 durable records remain replayable | BLOCKED | Compatibility tests through the actual durable service and codecs |

The list is an acceptance gate, not a progress claim. PR #300 defines the evidence required; PR #301 starts wiring the first bounded route, but no Gate B item is marked PASS until the tests exercise the actual durable service and commit boundary on the candidate SHA.

## 4. Gate C — manual SillyTavern acceptance

Manual acceptance must be performed against the exact candidate commit with the recorded SillyTavern version, extension version, Ollama version, intent model and model digest. Use a disposable campaign with deterministic fixtures/known starting state. For each scenario, capture a sanitized result, exact commit and run time. Do not put private player text, prompts or completions in a shared report.

### Execution sequence

1. **V2 baseline:** both V3 flags disabled. Verify a normal action, narration, durable commit, retry and chat isolation still work.
2. **Action preview only:** enable `CAMPAIGN_MANAGER_PLAYER_TURN_V3_ACTION_SHADOW_ENABLED=true`; keep `CAMPAIGN_MANAGER_PLAYER_TURN_V3_WORLD_FACTS_ENABLED=false`. Verify the same user-facing result and no V3 action execution or extra world mutation. Check the checkpoint is diagnostic and a retry does not regenerate it.
3. **Facts opt-in:** only after the fact-policy deterministic tests pass, enable both flags. Verify an explicit independent fact is persisted once through the ordinary atomic commit. Repeat with a quote/report, rumor, hypothesis, negative claim, uncertain claim and transfer without ownership; none may create an unauthorized fact.
4. **Discourse and ambiguity:** verify callback/ellipsis references are constrained to the same chat, and ambiguous references ask for clarification or abstain rather than selecting an arbitrary entity.
5. **Compound execution:** only after Gate B is fully green, verify a prerequisite success allows its dependent action to be planned from the virtual state; prerequisite failure blocks/skips it without leaking staged operations. Verify an unrelated accepted fact is retained independently.
6. **Challenges and recovery:** only after Gate B is fully green, verify manual-roll and clarification continuations resume the same node/checkpoint, retain the execution key, and do not re-run already committed mechanics.
7. **Delivery/reload:** duplicate external-turn delivery, application restart and same-chat retry must not duplicate a commit or regenerate the graph. A different chat must not see another chat's discourse/history.

### Manual result status for this PR

NOT RUN. The compound-execution items are BLOCKED by the runtime integration gaps in section 1. Do not mark them PASS by testing only the preview shadow or the isolated orchestrator tests.

## 5. Release decision and evidence bundle

The release gate consumes three independent sources:

1. The Ollama acceptance report's `acceptance_matrix`.
2. A runtime evidence JSON based on `tests/fixtures/v3_runtime_evidence_template_v1.json`.
3. A SillyTavern evidence JSON based on `tests/fixtures/v3_sillytavern_evidence_template_v1.json`.

Each evidence JSON uses `schema_version: 1`, a `run_manifest.campaign_manager_commit` field and a `checks` mapping. The full 40-character candidate SHA must match in the Ollama report's `run_manifest.git_commit` and in both runtime and SillyTavern evidence manifests. The CLI rejects manual evidence captured against a different commit. Check values must be one of `pass`, `fail`, `blocked`, or `not_run`; unknown check IDs and statuses are rejected. Mark an item `pass` only when there is a test/report from the exact candidate commit; a planned test or a unit-only substitute does not qualify.

After copying the templates and adding actual evidence, evaluate the bundle:

```powershell
python scripts/ci/v3_rollout_readiness.py `
  --candidate-commit <full-40-character-candidate-sha> `
  --acceptance-report <path-to-player-turn-v3-acceptance.json> `
  --runtime-evidence <path-to-runtime-evidence.json> `
  --sillytavern-evidence <path-to-sillytavern-evidence.json> `
  --output <path-to-v3-rollout-decision.json> `
  --require-review-eligible
```

Exit code 2 means one or more required gates is missing or non-passing. The command never changes configuration, feature flags, production routing or authority. Even when all gates pass, its strongest decision is `eligible_for_controlled_rollout_review`; a separate reviewed PR and explicit rollout decision are required before any change in authority.

**PR #300 / current PR #301 decision:** `HOLD V2`. Semantic Ollama acceptance and manual SillyTavern acceptance have not been run. PR #301 adds a separate execution flag, but it is false by default and requires action-shadow. Keep all V3 flags disabled for the production route until the same-node continuations, full deterministic durable integration and both live gates are accepted.

## 6. Privacy and evidence handling

- Share only aggregate, content-free reports and scenario/check IDs.
- Never include player utterances, prompts, completions, campaign context, secrets, literal evidence spans or unnecessary canonical IDs in PR comments or rollout artifacts.
- Keep any local debug output under access/retention controls separate from shareable quality reports.
- Record deterministic CI, live Ollama and manual SillyTavern results as three different evidence classes.
