# Discourse collaborators

## Responsibility

This package owns deterministic, bounded discourse signals used by intent
interpretation and conversation-reference resolution. It does not resolve
canonical entity IDs, authorize mechanics, or mutate campaign state.

## Collaborators and dependency direction

- `contracts.py` — immutable, content-preserving output records.
- `text.py` — shared normalization, quote masking and transcript field access.
- `topic_history_selector.py` — twelve-turn topic segmentation, explicit topic
  shifts, callback anchor scoring, tie reporting and bounded selection.
- `surface_mention_extractor.py` — literal pronoun/dative-clitic spans and
  local grammatical features.
- `speaker_signal_extractor.py` — speech predicates, named-NPC eligibility,
  quoted-NPC attribution and ambiguity-safe speaker hints.
- `renderer.py` — bounded Spanish-first hint rendering from collaborator
  results; history remains context, never current-turn evidence.

Allowed dependency direction:

```text
contracts / text
   |       |
   v       v
topic selector     surface mention extractor
                       |
                       v
                speaker signal extractor
                       |         |
                       +---------+
                            |
                            v
                         renderer
                            |
                            v
              DiscourseContextBuilder facade
```

`services.discourse_context.DiscourseContextBuilder` remains the stable public
facade. Existing context/turn consumers can continue using its class methods
without importing internal collaborators.

## Safety invariants

- Only the current utterance supplies literal current-turn source spans.
- Transcript and narration are bounded context and cannot become new player evidence.
- Named NPC speaker signals require active, visible entities and unique aliases.
- Quoted text is excluded from discourse-control markers and surface signal extraction.
- Ambiguous callback segments and ambiguous speaker aliases remain explicit/abstaining.
- Surface hints do not assign canonical identity or grant world-write authority.
- Rendering is byte bounded and never changes semantic payloads or domain state.

## Validation

The facade regression suite remains in `tests/test_discourse_context_builder.py`.
Direct collaborator contracts are in `tests/test_discourse_collaborators.py`.
Architecture tests enforce the collaborator dependency direction.
