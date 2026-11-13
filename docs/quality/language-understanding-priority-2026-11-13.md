# P0 — Shared natural-language understanding and intent resolution

**Priority:** P0 — highest active language-quality priority  
**Implementation:** the shared semantic foundation and conversation-scope hardening are integrated in PRs #215 and #216.  
**Verified baseline:** `main` at `868ae7ae29c6c1c0cfb5b3aaf181b630a0039ff6` (2026-11-13; PR #216 merge commit).  
**Acceptance:** live Ollama evaluation and full manual SillyTavern acceptance remain separate gates; this document does not mark them passed.

## 1. Implemented pipeline

1. Preserve the exact player utterance, request identity, active-character perspective and SillyTavern `conversation_id`.
2. Load bounded recent history from that same chat and filter world context through character visibility.
3. `MechanicsAdjudicator.understand()` makes one combined structured call for `PlayerIntentAnalysis` and a mechanics decision. Ollama receives the combined JSON Schema; providers without native structured generation use the compatibility path.
4. `PlayerIntentAnalysis.from_payload()` validates the response and grounds source excerpts, target mentions and attribution in player-authored evidence.
5. Deterministic entity/conversation resolvers map supported mentions to unique visible canonical entities; they never accept model-generated IDs and abstain on ambiguity.
6. The exact same analysis is passed to `LLMWorldExtractor`; future steps cannot skip unresolved earlier steps, and questions/plans/quotes/negations/reported outcomes are not treated as executed actions.
7. Typed operations are validated/applied by world/domain services. Rules code remains authoritative for mechanics and outcomes.
8. The durable resolution stores intent evidence. Clarification reinterprets the original input plus player answers; manual-roll continuation reuses the saved interpretation.
9. SillyTavern history and continuation are scoped to one chat. Migration 034 stores chat identity; migration 033 stores intent analysis.

Key implementation references: `models/player_intent_analysis.py`, `services/turns/mechanics_adjudicator.py`, `services/turns/intent_response_schema.py`, `services/context/entity_reference_resolver.py`, `services/context/conversation_reference_resolver.py`, `models/resolved_conversation_reference.py`, `services/turns/turn_resolution_service.py`, and `services/llm_world/llm_world_proposal_prompt_builder.py`.

## 2. Current v1 semantic contract

`PlayerIntentAnalysis` records utterance category (action/question/dialogue/report/plan/correction/mixed/unknown), ordered steps, active step and clarification state. Each `IntentStep` stores actor (player/NPC/other/unknown), a natural-language `action` string, modality, polarity, player-reported outcome, literal `target_mentions` and optional literal `attributed_to`.

The validator enforces version, exact field sets, enums, bounds, contiguous step order, source-evidence grounding and active-step constraints. This is an auditable untrusted interpretation, not a full semantic representation.

## 3. Remaining gaps found in source review

### Action and argument structure
`action` is free text and `target_mentions` is a flat untyped list. There are no explicit semantic roles for agent, patient/theme, recipient, source, destination, instrument, beneficiary, companion, location/path, precondition or cause. “I give the key to Mara” therefore lacks a first-class representation of the transferred object, recipient, source and resulting ownership transition.

### Relations
The world supports typed relationships, but the intent contract does not yet represent a grounded directed subject–predicate–object assertion with polarity, modality, attribution and time. It must distinguish “Mara is Aldric's sister” from a question, rumour, inference, hypothetical, quote or negative assertion. Predicates must map to supported domain relation types; the model must not invent new relation kinds.

### Objects and identity
A target mention does not say whether it denotes an NPC, place, item definition, unique item instance, event, faction or relation. Ownership, possession, equipment, container/location, condition, discovery, use and transfer are not explicit argument roles. Item templates and unique in-world instances must never be conflated.

### Discourse, references and corrections
PR #216's resolver examines at most six turns in the same chat, scans player input/narrative for visible names or aliases, and supports a bounded set of Spanish/English pronouns, demonstratives, “same/again” and curated “other [role]” patterns. It resolves only a unique visible candidate. It does not robustly model grammatical gender/number, semantic-type agreement, speaker attribution, topic/salience, broad ellipsis, long-distance references, paraphrases or correction chains. V1's correction category has no structured old/new values, correction target or scope (pending intent versus committed world fact); `attributed_to` remains a literal string.

### Evaluation
`language_understanding_corpus_v1.json` has 34 utterance cases (12 critical, repeated three times by the opt-in corpus test). `conversation_understanding_corpus_v2.json` has six deterministic resolver cases; these are not live-model coreference results. The live Ollama suite and full SillyTavern multi-chat workflow still require recorded acceptance evidence.

## 4. Safety boundaries to preserve

- Model output is evidence, never a canonical ID, permission, visibility grant, provenance assignment, dice result or write authorization.
- Every mention/relation endpoint must be grounded in player-authored evidence. Context may resolve an antecedent but cannot be cited as words the player said.
- IDs are attached only by deterministic application code after campaign, visibility, activity and semantic-compatibility checks.
- Unknown/hidden/ambiguous references remain unresolved; ask rather than guess.
- Mechanics and state transitions remain owned by deterministic rules/domain services.
- Preserve one shared interpretation. Do not add a third normal-path model call without measured evidence.
- Do not add embeddings/vector storage until evaluation proves lexical/graph retrieval is the limiting factor.

## 5. Acceptance gates

**CI:** re-run required Python/coverage, JavaScript, Ruff, Pyright and CodeQL checks on the current head. Keep migrations 033/034, cross-chat isolation, restart recovery, duplicate delivery, clarification and manual-roll tests in normal CI.

**Ollama:** run `python -m pytest -m real_llm -v -s` with exact model tag, Ollama version, generation settings, timeout and hardware recorded. Retain per-case outcome, latency, repair use and provider-call count. Do not log prompts, secrets or full responses; preserve every failure.

**SillyTavern:** use two real chats to prove neither can read/continue the other's history. Also verify same-chat references, ambiguous antecedents, multi-round clarification, correction, manual roll after restart, duplicate delivery and regeneration. Record backend SHA, extension revision and model details.

The implementation is integrated; the P0 language-quality phase is not accepted until live model and SillyTavern gates are documented as passed.

## 6. Recommended next implementation

After capturing that baseline, move to **structured semantic frames and grounded relations**, then richer discourse/reference resolution. See the [semantic-understanding next-phase plan](semantic-understanding-next-phase-2026-11-13.md). Do not resume broad gameplay expansion yet.
