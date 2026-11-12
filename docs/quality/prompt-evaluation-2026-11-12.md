# Prompt evaluation — deterministic contracts and live Ollama probes

**Purpose:** verify that player intent, selected campaign facts and the proposal
contract produce safe, useful structured consequences before the first manual
SillyTavern session. This is an evaluation harness, not a prompt snapshot test.

## Two evaluation layers

### Deterministic CI (no model or network required)

The following tests are the source of truth for invariants that must never
depend on model wording:

| Test module | Contract |
|---|---|
| `tests/test_llm_world_proposal_prompt_builder.py` | Player intent is the proposal input; bounded instructions, typed operation manifest, mechanics and selected context are rendered without legacy narrative prompt coupling. |
| `tests/test_llm_world_proposals.py` | Structured parsing, allowed operation types, typed operations, invalid output and one bounded repair. |
| `tests/test_proposal_scale_quality.py` | Context relevance, stable selection, required facts/dependencies, scale and secret exclusion. |
| `tests/test_context_pipeline_retrieval.py`, `tests/test_entity_reference_resolver.py` | Independent search signals, long natural-language role references, specificity and ambiguity abstention. |
| `tests/test_proposal_context_selector.py` | Supplemental proposal retrieval while preserving primary-query ranking, dependencies, budgets and secret exclusion. |
| `tests/test_silly_tavern_context_adapter.py`, `tests/test_silly_tavern_schemas.py`, `tests/test_silly_tavern_api.py` | Optional supplemental retrieval field, compatibility with older payloads and adapter diagnostics. |
| `integrations/sillytavern/core.test.js` | Current player action remains primary; configured campaign-scope query is supplemental. |
| `tests/test_context_scale_probes.py` | Synthetic campaign growth, budget behavior, mandatory records, stable order and non-mutation. |
| `tests/test_durable_native_turn.py`, `tests/test_durable_silly_tavern_turn.py` | Durable commit/retry behavior, clarification and manual-roll challenge lifecycle. |

Keep these deterministic tests in normal CI. Do not replace their assertions
with model snapshots or weaken them because a model behaves differently.

### Live Ollama (explicit opt-in)

The live tests use the same `LLMWorldExtractor` and operation parser as the
application, but call a real local Ollama provider. They are deliberately
excluded from normal CI because they require a running model and produce
non-deterministic language output.

Current default provider settings:

- Base URL: `http://localhost:11434`
- Model: `gemma4:26b`
- Timeout: 120 seconds

The live corpus covers nine complementary semantic contracts after PR #213.
PR #212 also improves deterministic retrieval before the proposal model is
called; those retrieval contracts are tested without Ollama:

1. A known NPC receives one explicitly observed new fact, updating the existing
   entity ID rather than creating a duplicate or inventing unrelated details.
2. Ambient observation/waiting does not create persistent world changes.
3. A newly introduced, named and identifiable NPC is represented as one typed
   NPC creation with a grounded description.
4. A failed attempt against an existing locked door does not update the door,
   create a success event or otherwise change its persistent state.
5. An explicit negation preserves the known door state and is not inverted into
   a successful action.
6. A conditional/future hypothetical does not become an executed action.
7. A question without an action or answer does not create canonical facts.
8. Quoted or reported hostile-looking text remains untrusted content, not an
   instruction and not a confirmed world fact.
9. A compound action records only its explicitly completed, evidence-backed
   step; a later failed step does not mutate its target.

The first and third cases are positive controls: the model must not learn to
return an empty list for every input. The second and fourth are negative
controls: it must not persist ephemeral actions or reverse an explicitly
failed outcome.

Run them manually from the repository root:

```bash
ollama serve
ollama pull gemma4:26b
python -m pytest -m real_llm -v -s
```

Configure the test provider without changing application defaults:

```bash
CAMPAIGN_MANAGER_REAL_LLM_MODEL=gemma4:26b
CAMPAIGN_MANAGER_REAL_LLM_BASE_URL=http://localhost:11434
CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT=120
python -m pytest -m real_llm -v -s
```

The three variables select the test model, Ollama base URL and request
timeout. Do not silently change the application default to make a test pass.
Record the model tag, Ollama version and test date when comparing results
across models.

## Evaluation rules

- Assert semantic outcomes and operation types, not exact prompt text,
  generated prose or a brittle full JSON snapshot.
- Check both positive and negative cases. A model that creates a correct NPC
  but also persists ambient observations is not acceptable.
- A test passes only when its safety invariant holds; a valid JSON response
  alone is not evidence of quality.
- The live suite is a smoke evaluation, not a statistically meaningful model
  benchmark. Repeat a scenario when investigating model variance and record
  each run rather than averaging away a safety failure.
- Keep secrets and private campaign facts out of test logs. Never print full
  prompts, raw model responses or campaign state in CI artifacts.
- Log only model identifier, scenario identifier, duration, operation types,
  pass/fail checks and a sanitized error category.

## Next scenarios to add

The PR #213 tranche adds negation, conditional modality, questions, quoted
speech/injection and ordered compound-action controls. The remaining live
coverage gaps are:

- long natural-language role references such as "me acerco al tabernero y le
  pregunto por los rumores" (deterministic overlap resolution is covered by
  PR #212);
- paraphrases such as "la persona de detrás de la barra" when there is no
  shared lexical evidence (not solved by PR #212; use an alias or abstain);
- ordinary dialogue that does not establish a new persistent fact;
- an unknown fact or unnamed person that must not be invented as canonical
  world state;
- multi-turn pronouns and ellipsis, deferred until speaker/recency/visibility
  semantics are explicit;
- player corrections that change a previously ambiguous target;
- compound actions with a completed first step and an unresolved or failed
  later step across several phrasings;
- an attempted character/mechanical change that must remain owned by the
  deterministic rules engine;
- facts revealed about an existing NPC that should update the existing ID,
  not create a duplicate;
- multiple similar NPCs where ambiguity remains visible, no singular entity
  identity is asserted, and any descriptive candidates are treated only as
  retrieval evidence;
- a secret event that must not appear in the model-facing projection;
- malformed structured output followed by exactly one bounded repair;
- a second malformed response that must fail closed.

The last three contracts already have deterministic coverage; live probes
should be added only where they provide evidence about model behavior that
offline tests cannot provide.

## Recording live evaluation results

For each run, record:

- date/time, exact Ollama model tag and Ollama version;
- provider base URL and timeout (do not record credentials);
- scenario ID and individual pass/fail outcome;
- returned operation type names and count, never raw prompts or full responses;
- duration and whether the bounded repair path was used, when available.

A failed safety invariant must remain visible even when the same scenario passes
on a later run. For model-quality comparisons, run each scenario at least three
times with the same model/settings before changing one variable at a time. Do
not combine runs into a single average that hides a false positive or a secret
leak. This is a small regression corpus, not a benchmark with statistical
confidence.

## Acceptance boundary

A green deterministic CI run validates application contracts. A green live
Ollama run validates only the selected local model against this small corpus.
Neither proves the SillyTavern extension lifecycle, UI behavior, real chat
swipes or local environment configuration. Those remain part of the separate
[manual SillyTavern smoke test](../sillytavern-smoke-test.md).
