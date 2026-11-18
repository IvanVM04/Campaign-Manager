> **Historical implementation record — PR #253 baseline.** This file records the taxonomy/normalization work and its then-current model metrics. PR #255 added later discourse and compound-intent changes; the old metrics are not a post-#255 baseline. Use the [current quality roadmap](quality-roadmap-2026-11-18.md) for current priorities.

# Semantic understanding hardening — 2026-11-17

## Executive summary

This implementation responds to the first local semantic-frame predicate holdout run with Gemma 4 12B Q4_K_M on Ollama 0.40.16, using `think=false`.

The recorded baseline was:

| Metric | Result |
|---|---:|
| Action predicate surface F1 | 0.9714 |
| Relation predicate surface F1 | 0.2143 |
| Aggregate semantic-slot F1 | 0.6349 |
| Provider calls / scenarios | 36 / 20 |
| Elapsed time | 671.547 s |

The run was made from the PR #251 feature branch. It did not include the prompt/schema taxonomy work that was later committed in PR #252's feature-branch merge. This implementation therefore carries that taxonomy work forward onto `main` and adds independent deterministic, evidence-bound normalization. The baseline is historical and must not be compared directly to a new run until the updated scorer has produced its new baseline.

## Findings from the run and source audit

### 1. Action-frame family and role errors were not isolated

The model copied surface action predicates well, but classified explicit transfer and combat predicates as generic interaction. It also missed or confused roles such as `theme`, `recipient`, `patient`, `instrument`, `container`, `source`, `path` and `destination`.

The prior prompt/schema described a narrow distinction between communication and interaction. It did not provide an operational taxonomy that distinguished transfer, item use, combat, movement, perception and the remaining families, nor did it define argument roles in context.

### 2. Relation extraction lacked clear lexical and family boundaries

Observed output included relation predicates with argument-introducing prepositions (`pertenece a`, `jura lealtad a`) and negation markers (`no pertenece`). Family confusion included ownership, possession and membership. Reported attribution and temporal expressions were also omitted in some cases.

### 3. Optional ungrounded output could invalidate an otherwise useful analysis

The domain validator correctly rejects evidence that is not present in the current utterance and step excerpt. However, one unsupported optional target mention or action argument could reject the complete semantic response, even where the remaining structure was valid. Existing provider-boundary cleanup covered some attribution cases but not all optional semantic mention arrays.

### 4. Evaluation dimensions were coupled

The previous scorer stopped argument matching when the action family was wrong and stopped relation field scoring when endpoint direction was wrong. This conflated independent errors. A leading article or Spanish contraction difference could also prevent endpoint matching before the predicate was even evaluated.

## Implementation

### Prompt and structured schema taxonomy

The semantic interpreter prompt and JSON Schema now describe:

- Specific action families and when to prefer them over generic `interaction`.
- Distinctions between `patient`, `theme`, `recipient`, `instrument`, `container`, `destination`, `source`, `path` and `companion`.
- Coarse object-kind hints based only on literal mentions.
- Relation families including ownership, possession, membership, employment, allegiance, protection, friendship, hostility, kinship, service, knowledge, containment and part-of.
- Lexical predicate boundaries: preserve multiword predicates, but keep argument-introducing prepositions and negation in their own fields.
- Explicit preservation of reported attribution, negation and temporal expressions.

### Evidence-bound surface normalizer

`services/turns/semantic_surface_hints.py` adds conservative patterns for common Spanish constructions. It is a supplement to the LLM, not a replacement grammar.

For actions, high-confidence local patterns can correct a frame family and rebuild arguments for explicit transfer, item-use, combat, movement, perception and hiding-location constructions. The rules preserve the model's literal predicate and only create argument mentions that occur in the current step excerpt.

For relations, explicit constructions can generate or replace a relation claim for one step. Initial supported patterns cover employment, belonging, allegiance, protection, hostility, friendship, part-of, ownership, possession, kinship, service, knowledge and containment. Negation, reported attribution and temporal prefixes are kept in polarity, modality and temporal fields rather than merged into the predicate.

A step with multiple plausible relational clauses, a conditional lead-in or an unsupported construction is left to the LLM. The surface layer does not guess through ambiguity.

### Safe provider-boundary cleanup

Before strict domain decoding, the interpreter removes only optional target mentions, action arguments and relation claims that cannot be grounded in both the current evidence and their step excerpt. It does not reconstruct a missing predicate, actor, entity identity or required field; those cases remain strict validation failures.

For a single-step utterance, the evidence excerpt may be widened to the complete literal input only when a supported relation construction requires a literal reported speaker or temporal prefix that the model omitted from its shorter excerpt. The widened text is copied verbatim, bounded by the existing 300-character step excerpt limit, and is never sourced from conversation history.

### Independent evaluation

The scorer evaluates action arguments across all returned action frames even when family is wrong. Relation family, polarity, modality, attribution and temporal fields are evaluated against an unordered endpoint pair; relation direction remains an independent ordered-pair metric. Mention comparison ignores only leading Spanish articles/contractions for scoring; the normalized text is never written back into the analysis.

## Safety and non-goals

- Does not modify canonical entity resolution or introduce entity IDs into model output.
- Does not grant write authority, resolve mechanics or apply world operations.
- Does not relax literal evidence validation for predicates or required fields.
- Does not use conversation history to reconstruct current-turn mentions.
- Does not copy held-out utterances or gold labels into prompts.
- Does not modify `semantic_frame_corpus_holdout_v1.json` or `semantic_frame_predicate_gold_v1.json`.
- Does not claim complete Spanish grammar coverage. Rules are intentionally narrow; ambiguous and compound language remains under LLM interpretation and existing validation.

## Offline validation

~~~powershell
python -m pytest tests/test_semantic_surface_hints.py tests/test_predicate_evaluation.py tests/test_intent_speech_act_contract.py tests/test_semantic_frames.py -q
python -m pytest tests/test_real_llm_semantic_holdout.py -m "not real_llm" -q
ruff check services/turns/semantic_surface_hints.py services/turns/intent_interpreter.py services/turns/intent_response_schema.py tests/test_semantic_surface_hints.py tests/semantic_frame_evaluation.py tests/test_predicate_evaluation.py tests/test_intent_speech_act_contract.py
pyright services/turns models tests
~~~

## Live acceptance

Use the same model and quantization as the reported baseline where possible, keep `CAMPAIGN_MANAGER_REAL_LLM_THINK=false`, set the exact commit SHA, and run the full 20-scenario holdout. Also retain the JSON report and compare:

- Action-frame family accuracy and argument roles.
- Action predicate surface F1.
- Relation predicate surface F1.
- Relation direction, family, polarity, modality, attribution and temporal fields.
- Invalid-response counts and evidence-validation fields.
- Critical false persistent changes and secret leaks.

A better surface predicate score alone is not sufficient. Do not accept a rise in relation recall if it creates unsupported relation claims or regresses action roles, direction, abstention or safety gates. Re-run with reasoning enabled separately if an A/B comparison is needed; do not mix settings in one reported baseline.
