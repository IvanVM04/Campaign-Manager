# Prompt and semantic evaluation — deterministic contracts and live Ollama

**Purpose:** evaluate whether the integrated pipeline understands player language, retrieves relevant world evidence, proposes only supported consequences and preserves durable/SillyTavern continuity. This is an evaluation guide, not a prompt snapshot test.

## Deterministic CI

| Test / fixture | Contract |
|---|---|
| `tests/test_player_intent_analysis.py` | Strict v1 schema, enums, bounds, evidence grounding, step order and active-step invariants. |
| `tests/test_mechanics_adjudicator.py`, `tests/test_turn_mechanics_integration.py` | Mechanics gating and shared interpretation hand-off. |
| `tests/test_conversation_reference_resolver.py` | Conservative pronoun/same-object/other-role resolution against visible canonical entities; ambiguity abstention. |
| `tests/test_conversation_understanding_corpus.py` + v2 fixture | Six deterministic resolver cases; not an LLM benchmark. |
| `tests/test_entity_reference_resolver.py` | Canonical names, aliases, descriptive matching and ambiguity. |
| `tests/test_llm_world_proposal_prompt_builder.py`, `tests/test_llm_world_proposals.py` | Shared semantic input, bounded prompt, operation contract, parser and compact repair. |
| Turn codec/repository/migration tests | Durable intent evidence, migrations 033/034, recovery and chat scope. |
| SillyTavern API/schema/adapter/extension tests | Required conversation identity and chat-scoped continuation paths. |
| Context selector/retrieval/scale tests | Relevant context, dependencies, budgets, stable ordering and secret exclusion. |

Keep deterministic tests independent of Ollama, network access and a running SillyTavern instance. Do not weaken them to accommodate model failures.

## Live Ollama (explicit opt-in)

The `real_llm` suite uses the actual provider and production interpretation/proposal boundaries. It is excluded from normal CI.

Default documented settings: `http://localhost:11434`, `gemma4:26b`, timeout 120 seconds. Override only for deliberate comparisons:

```bash
CAMPAIGN_MANAGER_REAL_LLM_MODEL=gemma4:26b
CAMPAIGN_MANAGER_REAL_LLM_BASE_URL=http://localhost:11434
CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT=120
python -m pytest -m real_llm -v -s
```

Record exact model tag/digest, Ollama version, generation settings, timeout and hardware class. Do not assume the configured local model matches the documented default.

## Current corpora

### Utterance understanding — 34 labelled scenarios

Fixture: `tests/fixtures/language_understanding_corpus_v1.json`. It contains Spanish/English cases for attempted actions, questions, plans/conditionals, player/NPC dialogue, reported speech, observation, failure/completion/partial outcomes, negation/cancellation, uncertainty, compound steps, correction classification, ambiguous pronouns and quoted/untrusted instructions. Twelve are critical and are repeated three times by `test_real_ollama_meets_shared_player_intent_corpus_v1`; the other cases run once in that corpus test.

### Conversation references — six deterministic scenarios

Fixture: `tests/fixtures/conversation_understanding_corpus_v2.json`. It covers unique and ambiguous pronoun antecedents, “other guard”, same-object, invisible antecedent and new proper name. These cases test `ConversationReferenceResolver` as deterministic code; they do not measure live model coreference, grammatical agreement, broad ellipsis or correction chains.

### Current real-LLM test functions

Focused proposals cover updating an existing NPC, avoiding ephemeral changes, introducing an NPC, preserving a locked door after failure, rejecting non-executed/quoted intent, retaining only the confirmed compound-action step and the shared v1 intent corpus. Passing these cases is a narrow regression signal, not proof of general language understanding.

## Recording a run

Run `python -m pytest -m real_llm -v -s` from the repository root. Retain timestamp, commit SHA, model/version/settings, scenario ID, pass/fail result, operation type/count, latency, repair usage and provider-call count. Preserve every failure even when a later repeat passes. Never log full prompts, raw responses, secrets or private campaign state.

## Metrics — report by family

- Intent category, actor, modality, polarity, outcome and step-order accuracy.
- Source excerpt and target-mention grounding.
- Reference-link precision/recall and ambiguity abstention.
- Required/forbidden context precision and recall; dependency completeness.
- Relation direction/polarity and object/argument-role accuracy as those labels are added.
- Operation precision/recall, duplicate identity/instance rate and false persistent changes.
- Secret leakage (must be zero), cross-chat isolation and durable continuation.
- Malformed response/repair rate, provider-call count and latency distributions.

Do not merge omissions and false positives into one score. Unsupported persistent changes are more severe than a clarification request.

## Known gaps and next corpus tranche

The current corpus is not broad enough to establish robust understanding. Add cases for agent/patient/recipient/source/destination/instrument roles; object definition versus item instance, possession, equipment and transfer; directed relations (kinship, ownership, allegiance, membership, employment, containment and spatial relations); attributed NPC statements versus observation/rumour/inference; Spanish/English grammatical and semantic-type agreement; multi-turn ellipsis, topic shifts, speaker attribution and competing antecedents; corrections to target/action/recipient; and temporal/causal language.

The [next-phase plan](semantic-understanding-next-phase-2026-11-13.md) specifies a path to at least 100 labelled cases and a held-out evaluation tranche.

## Acceptance boundary

Green deterministic CI validates application contracts, not model quality. A green Ollama run validates only the selected model against the executed cases. Neither proves the SillyTavern extension lifecycle or real multi-chat behavior.

Keep P0 open until current required CI passes, the 34-case utterance corpus/focused live tests are recorded with pinned settings, the manual two-chat/recovery SillyTavern checklist passes, and no critical false persistent change or secret leak remains unresolved. See the [manual SillyTavern smoke test](../sillytavern-smoke-test.md).
