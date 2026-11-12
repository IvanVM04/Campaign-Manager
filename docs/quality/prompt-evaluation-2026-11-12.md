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

The live tests currently cover:

1. A structured proposal is returned for an explicitly introduced NPC.
2. Ambient observation/waiting does not create persistent world changes.
3. An explicitly introduced NPC is represented as a typed NPC creation.
4. A failed attempt to open a locked door is not recorded as a successful
   world change.

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

Before expanding the prompt or changing the model, extend the live corpus with
these semantic cases:

- ordinary dialogue that does not establish a new persistent fact;
- an unknown fact or unnamed person that must not be invented as canonical
  world state;
- an attempted character/mechanical change that must remain owned by the
  deterministic rules engine;
- a secret event that must not appear in the model-facing projection;
- malformed structured output followed by exactly one bounded repair;
- a second malformed response that must fail closed.

The last three contracts already have deterministic coverage; live probes
should be added only where they provide evidence about model behavior that
offline tests cannot provide.

## Acceptance boundary

A green deterministic CI run validates application contracts. A green live
Ollama run validates only the selected local model against this small corpus.
Neither proves the SillyTavern extension lifecycle, UI behavior, real chat
swipes or local environment configuration. Those remain part of the separate
[manual SillyTavern smoke test](../sillytavern-smoke-test.md).
