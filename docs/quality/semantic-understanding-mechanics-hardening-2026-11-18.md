# Semantic understanding and mechanics hardening — 2026-11-18

## Why this change exists

The local evaluation on commit `74454130125060e56951f41a48a022be2dc3e7ea`
used `gemma4:12b-it-q4_K_M`, Ollama `0.40.16`, thinking disabled and 20
semantic-frame scenarios (36 provider calls). The semantic-frame holdout passed
with semantic-slot F1 0.973, recall 1.0, action-predicate F1 1.0 and
relation-predicate F1 0.9474 (two false positives).

The separate language-understanding holdout failed on critical cases involving
conditional plans, reported failures, corrections, compound actions, NPC
attribution and epistemic uncertainty. The integrated production-path probe
also failed before the rules engine could resolve its natural-1 roll: the
mechanics model returned localized/explanatory skill and ability strings and
the backend rejected the payload.

These are different failure classes and must remain separately observable.

## Mechanics response contract

The mechanics-only provider schema previously required only `decision`, while
the typed parser required different fields for checks, clarification and
`none`. Its string fields also allowed localized values that the rules engine
could not convert to `Skill` or `Ability`.

The mechanics-only schema now has one fixed object shape with nine required
keys:

- `decision`
- `question`
- `dc`
- `advantage`
- `disadvantage`
- `modifier`
- `reason`
- `skill`
- `ability`

Fields not owned by the selected decision are explicitly null. Skill and
ability use the exact lowercase enum values exported by the D&D 5e rules
engine. The backend adapter validates the selected variant, checks nullability
and passes a compact representation to the existing typed decision parser.
The older combined compatibility contract remains separate.

The mechanics prompt explicitly forbids translated or explanatory identifiers.
The rules engine remains responsible for deriving a default ability from a
skill when `ability` is null, and for all rolls and outcomes.

## Evidence-local language normalization

A new small normalizer runs after untrusted-surface sanitization and before
strict domain decoding. It only applies rules when the utterance contains
unambiguous local evidence:

- A direct interrogative addressed to the DM is a question, not an actionable
  player attempt. An explicit first-person speech verb plus a recipient is
  dialogue even when the quoted content is imperative or interrogative.
- A two-step sequence preserves an explicitly observed/perceptual first step
  before a separately expressed later attempt; the second step remains active.
- A single-step conditional future is a plan with a null active-step pointer.
- An explicit attempted action followed by a lexical failure clause is marked
  as resolved with `reported_outcome=failure`. A two-step model split is
  collapsed only when step two is the failure clause and there are no relation
  claims that would need re-indexing.
- Explicit “not X, but Y” correction language is marked as correction, not a
  new attempt.
- A literal speaker, reporting predicate and `que` clause preserve attribution
  inside the step excerpt. Indefinite speakers remain `other`.
- Explicit epistemic markers mark the claim uncertain and clear the active
  action pointer. They do not become confirmed world facts.

These rules do not resolve canonical entities, create IDs, set visibility,
grant permissions, invent predicates, or authorize world writes. Multi-step
and ambiguous cases remain model-led and subject to the strict domain
validator. The original held-out fixtures are not modified; unit regressions
use separate paraphrased utterances.

The interpreter emits only content-free rule identifiers when a rule applies.

## Live evaluation and reproducibility

The language holdout now records model tag/digest, Ollama version, timeout,
thinking value, commit, hardware label, family metrics, failure counts and a
content-free provider usage summary in JUnit properties. It still does not log
prompts or completions.

The integrated probe applies `CAMPAIGN_MANAGER_REAL_LLM_THINK` to each role
unless that role has its own `CAMPAIGN_MANAGER_LLM_<ROLE>_THINK` setting. It records per-role model, digest, timeout, thinking value and safe
usage totals before re-raising a preparation failure, so diagnostics survive
a failed mechanics or proposal stage.

## Validation

Offline regression scope:

```powershell
python -m pytest tests/test_mechanics_adjudicator.py tests/test_modular_language_pipeline.py tests/test_intent_surface_normalization.py -q
python -m pytest tests/test_predicate_evaluation.py -q
```

Live acceptance remains opt-in and must be rerun against the exact model tag
and Ollama installation used for the previous baseline:

```powershell
python -m pytest tests/test_real_llm_semantic_holdout.py -m real_llm -k "held_out_language_understanding_corpus_v1" -v -s
python -m pytest tests/test_real_llm.py -m real_llm -k "integrated_pipeline_does_not_advance_failed_compound_action" -v -s
```

This PR does not claim a new live-model pass. The semantic-frame result from
the prior commit remains a historical measurement; after merging, rerun the
semantic-frame holdout as well to ensure the language normalizations did not
cause regressions.

## Deliberate remaining limitations

The surface rules intentionally do not attempt to split arbitrary compound
sentences, infer all ellipses, or classify every indirect question. Those
remain model responsibilities. The real integrated probe must pass before
claiming that the production interpreter → mechanics → proposal handoff is
accepted with this model.
