# PR #223 — Advanced discourse understanding

**Base:** `main` after PR #222, commit `48116ce879df5abb6dae9995ba854dbc44bc538e`.
**Branch:** `feat/223-advanced-discourse-understanding`.
**Scope:** bounded discourse interpretation; no domain write authority changes.

## Problem

The shared understanding path already represents typed semantic frames and
auditable discourse evidence, but reference resolution used only six turns,
topic continuity was a flat repetition bonus, dialogue was only divided
between player input and narrator text, and grammatical agreement was
unavailable. Elliptical messages and cross-turn instructions therefore
remained fragile.

## Implementation

- Add `DiscourseContextBuilder`, a deterministic provider-independent source
  of discourse hints.
- Expand same-chat history to twelve turns in adjudication, proposal context,
  retrieval and both reference resolvers.
- Detect explicit topic shifts and callbacks. Ordinary lookup is scoped to the
  active topic segment; an explicit callback may reopen the bounded window but
  cannot bypass confidence or ambiguity checks.
- Add cues for likely ellipsis and deictic expressions. An omitted action may
  be completed only when its antecedent is unique, visible and still pending.
- Attribute quoted speech only when a unique active visible NPC is explicitly
  labelled as its speaker. Other names inside the quote are not attributed.
- Extend `DiscourseEvidence` with an optional typed NPC speaker entity ID and
  widen its recency-rank validation to twelve.
- Apply grammatical agreement only where a literal local article/apposition
  appears near the antecedent (for example, "la guardia Mara"). Never infer
  gender/number from a proper name or entity category. Plural pronouns abstain
  because no group-entity identity contract exists.
- Preserve one shared model interpretation, one normal provider call, immutable
  correction semantics, visibility checks, typed ID namespaces and deterministic
  domain validation.

## Files and tests

- `services/context/discourse_context_builder.py`
- `models/discourse_evidence.py`
- `services/context/conversation_reference_resolver.py`
- `services/context/world_reference_resolver.py`
- `services/turns/mechanics_adjudicator.py`
- `services/turns/turn_resolution_service.py`
- `services/llm_world/llm_world_proposal_prompt_builder.py`
- `tests/test_discourse_context_builder.py`
- Expanded `tests/test_conversation_reference_resolver.py`
- Updated context/turn contracts and the language-understanding roadmap.

## Safety and compatibility

- No model-supplied canonical IDs, permissions, visibility grants or write authority.
- No inference of personal gender from names, voice or stereotypes.
- No NPC attribution without an explicit unambiguous label and a visible active NPC.
- Player, narrator and NPC speech remain separate evidence sources.
- Explicit callbacks reopen only the bounded history; ambiguity still forces clarification.
- Plural pronouns never resolve to an arbitrary individual.
- Existing semantic intent schema v1/v2 and durable turn records are unchanged.
- No database migration, vector database, extra normal-path provider call,
  additional provider service or new dependency.

## Validation

CI must run Python tests/coverage, Ruff, required and repository-wide Pyright,
JavaScript tests and CodeQL. Regression checks cover twelve-turn references,
topic boundary/callback handling, NPC speaker ambiguity/visibility,
grammatical agreement and plural abstention.

Live Ollama evaluation must record model tag/digest, Ollama version, generation
parameters and hardware. Manual SillyTavern acceptance must cover at least two
chats, explicit NPC dialogue, topic switches/callbacks, ellipsis, distant
references, multi-round clarification, restart and replay. Neither live gate
is claimed by deterministic CI.
