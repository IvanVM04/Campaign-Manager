# Semantic prompt evaluation — deterministic contracts and live Ollama

**Purpose:** evaluate the integrated interpretation/proposal pipeline without confusing deterministic application guarantees with live model quality.

## 1. Deterministic CI

| Test / fixture | Contract |
|---|---|
| `tests/test_player_intent_analysis.py` | V1 interpretation shape, enums, evidence grounding, order and active-step invariants. |
| `tests/test_semantic_frames.py` | V2 typed action frames, role/kind validation, relation direction/modality, exact evidence, no model IDs, v1 compatibility and durable v2 codec round-trip. |
| `tests/test_mechanics_adjudicator.py` | Combined adjudicator returns a shared interpretation; v2 schema requires action frames/relation claims while v1 payload decoding remains compatible. |
| `tests/test_turn_mechanics_integration.py` | Shared interpretation is reused for mechanics and proposal hand-off. |
| `tests/test_conversation_reference_resolver.py` and corpus test | Conservative multi-turn resolution against visible entities; ambiguity abstention. |
| `tests/test_entity_reference_resolver.py` | Canonical names, aliases, descriptive matching and ambiguity. |
| LLM proposal prompt/parser tests | V2 frame guidance, shared semantic input, bounded prompt, typed operations and bounded repair. |
| Turn codec/repository/migration tests | Fingerprinted durable evidence, v1/v2 analysis recovery, migrations 033/034 and chat scope. |
| SillyTavern API/schema/adapter/extension tests | Required conversation identity and chat-scoped continuation paths. |
| Context selector/retrieval/scale tests | Relevant context, dependencies, budgets, stable ordering and secret exclusion. |

Keep deterministic tests independent of Ollama, network access and a running SillyTavern instance. Do not weaken them to accommodate model failures.

## 2. Live Ollama (explicit opt-in)

The `real_llm` suite uses the actual provider and production interpretation/proposal boundaries. It is excluded from normal CI.

Default documented settings are `http://localhost:11434`, `gemma4:26b` and timeout 120 seconds. Run:

```bash
CAMPAIGN_MANAGER_REAL_LLM_MODEL=gemma4:26b
CAMPAIGN_MANAGER_REAL_LLM_BASE_URL=http://localhost:11434
CAMPAIGN_MANAGER_REAL_LLM_TIMEOUT=120
python -m pytest -m real_llm -v -s
```

Record exact model tag/digest, Ollama version, generation settings, timeout and hardware. Do not assume the user's actual model matches the documentation default.

## 3. Current corpora and what they prove

### Utterance understanding — 34 labelled scenarios

Fixture: `tests/fixtures/language_understanding_corpus_v1.json`. It covers Spanish/English attempts, questions, plans/conditionals, player/NPC dialogue, reported speech, observations, failures/completion/partial outcomes, negation/cancellation, uncertainty, compound steps, correction classification, ambiguous pronouns and quoted instructions. Twelve critical cases are repeated three times; the rest run once.

The production adjudicator now expects the v2 output envelope. The existing corpus assertions primarily verify category, active step, clarification, actor, modality, polarity and player-reported outcome. V2 parser validation additionally checks frame structure and evidence, but the corpus does not yet comprehensively measure whether the model assigns every semantic role or relation correctly.

### Conversation references — six deterministic corpus scenarios plus focused regressions

Fixture: `tests/fixtures/conversation_understanding_corpus_v2.json`. It covers unique/ambiguous pronoun antecedents, “other guard”, same-object, invisible antecedent and new proper name. PR #219 adds focused deterministic regressions for player-input versus narrator evidence, semantic-kind filtering, six-turn bounds, auditable candidate scores and abstention reasons. These are application resolver cases, not live model coreference accuracy.

The resolver does not infer grammatical gender/number because canonical entities do not currently expose reliable values, and it does not fabricate NPC speaker labels from unstructured narration. The pending-correction tests protect a pure application helper; they do not measure whether the model can emit corrections.

### Semantic-frame unit corpus

`tests/test_semantic_frames.py` currently covers transfer-role extraction, item-instance hints, relation direction/attribution/reported modality, negative/question/conditional relation metadata, evidence rejection, model-ID rejection, missing-step rejection, v1 shape preservation and durable v2 recovery. These are parser/value-object tests; they do not prove Ollama produces correct frames for natural language.

### Semantic frames — ten live scenarios

Fixture: `tests/fixtures/semantic_frame_corpus_v1.json`. It contains ten
Spanish examples spanning transfer recipients, instruments, movement source
and destination, kinship, ownership, negative ownership, questioned ownership,
conditional kinship, reported kinship and spatial containment. Four critical
cases repeat three times in `test_real_ollama_meets_semantic_frame_corpus_v1`.

The live assertions check selected action-frame family/role/mention/kind slots
and relation subject/object/predicate/family/polarity/modality/attribution.
This is an initial regression tranche, not a statistically meaningful
benchmark. The full held-out evaluation remains PR #220.

## 4. Recording a run

Run `python -m pytest -m real_llm -v -s` from the repository root. Retain timestamp, commit SHA, exact model/version/settings, scenario ID, pass/fail outcome, operation types/count, latency, repair use and provider-call count. Preserve every failure even when a later repeat passes. Do not log full prompts, raw responses, secrets or private campaign state.

## 5. Metrics — report by family

- Category, actor, modality, polarity, reported outcome and step-order accuracy.
- Action-family classification and semantic argument role/mention accuracy.
- Object-kind accuracy, especially item definition versus item instance.
- Relation subject/object direction, predicate, family, polarity, modality and attribution accuracy.
- Literal evidence grounding and no-invented-mention rate.
- Entity-link precision/recall and ambiguity abstention.
- Required/forbidden context precision/recall and dependency completeness.
- Operation precision/recall, duplicate identity/instance rate and false persistent changes.
- Secret leakage (must be zero), chat isolation, durable continuation and repair rate.
- Provider-call count and first-response/end-to-end latency distributions.

Do not combine omissions and false positives into one score. Unsupported persistent changes are more severe than a clarification request.

## 6. Next corpus tranche

PR #220 should add at least 100 balanced labelled cases with a held-out tranche. Include: agent/patient/recipient/source/destination/instrument; pickup/drop/transfer/equip/store/use; definitions versus instances; owner versus holder; kinship, property, membership, allegiance, employment, containment and spatial relations; directed inverse claims; questions, negations, rumours, reported speech and conditional claims; Spanish/English agreement; topic shifts, ellipsis and corrections; temporal/cause language; multiple plausible objects; secrets; and positive/negative controls.

Each case should specify expected interpretation constraints, allowed/forbidden operation families, required/forbidden context facts and abstention behavior. Avoid exact JSON snapshots when several semantic representations are equally valid; assert roles and invariants.

## 7. Acceptance boundary

Green deterministic CI proves application contracts, not model quality. A green Ollama run proves only the selected model against the executed scenarios. Neither proves the SillyTavern extension lifecycle or actual multi-chat behavior.

Keep P0 open until required CI passes, live Ollama results are recorded with pinned settings, the real two-chat/recovery SillyTavern checklist passes, and no critical false persistent change or secret leak remains unresolved.
