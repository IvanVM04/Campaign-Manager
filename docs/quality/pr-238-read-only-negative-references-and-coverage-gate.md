# PR #238 — Read-only negative references and reliable coverage enforcement

## Why this follow-up exists

PR #237 separated conversation-reference comprehension from world-write
eligibility and changed pending clarification into a typed patch contract.
Reviewing the merged implementation exposed two remaining quality issues:

1. The reference resolver still discarded negative steps and negative relation
   claims. That means a pronoun or named participant in a negated statement
   could remain unresolved even though identifying the referent is a
   read-only comprehension task.
2. The PR #237 deterministic test job was marked successful despite printing
   that combined coverage was below the repository's enforced threshold.

This follow-up preserves PR #237's architecture and does not weaken any
authorization or evidence boundary.

## Evidence from the merged PR #237 run

The Tests workflow run `43845634220` completed with all jobs marked
successful. Its Python test log recorded:

- 1,887 passed, 21 deselected;
- 84.94% combined line/branch coverage;
- the explicit message
  `FAIL Required test coverage of 85.0% not reached. Total coverage: 84.94%`.

The workflow did not fail the job for that threshold message. The repository
configures `fail_under = 85` in `pyproject.toml`, but the CI step relied only
on pytest-cov's session hook. PR #238 adds an independent
`coverage report` invocation after pytest so Coverage.py's own configured
threshold controls the job exit status as well.

## Root-cause and design changes

### 1. Resolve negative and uncertain mentions read-only

`ConversationReferenceResolver` now treats reference extraction as
comprehension rather than authorization:

- negative and uncertain steps with eligible modalities are still considered;
- `IntentModality.NEGATED` is eligible;
- literal relation subjects, objects and attributions are considered even
  when their relation polarity is negative or uncertain.

The resolver returns only evidence-backed references or clarification
requests. It does not grant mechanics permission, allow a proposal, or mutate
the world. The existing downstream checks remain unchanged:

- mechanics remains conditional on an actionable, validated active step;
- typed world-reference resolution remains behind
  `analysis.allows_world_proposal`;
- `LLMWorldExtractor` and persistent writes remain behind the existing
  proposal-authorization path.

The tests explicitly assert that the negative report/relation examples have
`allows_world_proposal == False` while their visible references can still be
resolved.

### 2. Enforce coverage independently

The workflow adds a separate step:

```bash
python -m coverage report
```

It runs after the deterministic pytest/coverage step and package summary.
Coverage.py reads the repository's configured `fail_under = 85` and determines
the exit status. CI therefore cannot pass merely because pytest-cov printed a
threshold failure but returned success.

The threshold is not lowered and the report is not excluded from the gate.

### 3. Strengthen correction-contract regression coverage

Additional deterministic cases exercise invalid correction status combinations:

- `corrected` without a patch;
- `needs_clarification` without a question;
- blank or overlong clarification questions;
- `no_change` combined with a question or patch;
- unsupported status and incomplete top-level contract.

A separate invariant test confirms that an interpreter result cannot alter
the pending action text or other analysis fields outside the typed patch
slots. This protects the central PR #237 guarantee that the backend applies
only deterministic, typed corrections.

## Safety boundaries

- Negative reference resolution is read-only and does not make an analysis
  eligible for persistent writes.
- No polarity, modality, actor, category or evidence is rewritten by the
  resolver.
- No evidence validators are relaxed.
- No model-produced IDs or permissions are introduced.
- Mechanics, typed world-reference resolution and proposal execution retain
  their existing gates.
- The configured 85% coverage minimum remains unchanged.

## Acceptance criteria

- The new negative NPC report test resolves a uniquely evidenced pronoun
  while keeping `allows_world_proposal` false.
- The negative relation test resolves both literal endpoints without enabling
  proposal authorization.
- The invalid correction status matrix and non-patch state invariant tests
  pass.
- The CI workflow fails when combined coverage is below 85.0% and passes only
  when the configured floor is met.
- Deterministic tests, Ruff, both Pyright checks, JavaScript tests and CodeQL
  are green.
- Repeat the pinned local Gemma 4 12B discourse holdout and multi-turn
  correction holdout on this implementation. CI success is not a substitute
  for live-model semantic acceptance.

## Explicit non-goals

This PR does not attempt to solve all dialogue/report/question classification,
callback recovery, long-distance coreference or ellipsis quality. It does not
change Ollama model selection, add embeddings/vector storage, or introduce
additional LLM agents. Those remain separate measured work after the
read-only reference and correction contracts are reliable.
