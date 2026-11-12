> **Historical document — superseded by the 2026-11-12 legacy-retirement cleanup.**
> The narrative-first extractor, static legacy prompt builder, deprecated
> `POST /integration/turn`, legacy turn service and runtime snapshot
> reconciliation described below have been removed. Migration 029 archives
> existing non-null snapshot JSON in `turn_snapshot_archive`. Do not treat
> the recommendations in this historical report as current implementation
> instructions; see [the current architecture audit](architecture-audit-2026-11-12.md)
> and [turn pipeline contract](turn-pipeline-compatibility.md).

# Legacy narrative prompt decomposition — 2026-11-12

## Purpose

Record the behavior-preserving decomposition of the static instructions used by
LLMWorldPromptBuilder. This is a maintenance change to the legacy narrative
extraction path. It does not alter the active durable player-intent proposal path.

## Result

The former 2,193-line llm_world_prompt_builder.py no longer owns the entire
static instruction body. The body is split into the following ordered modules
under services/llm_world/legacy_prompt_sections/:

1. role_and_fact_rules.py — role, input safety and confirmed facts.
2. entity_rules.py — entity creation and updates.
3. item_rules.py — item definitions, instances and transfers.
4. resource_rules.py — resource changes.
5. relation_rules.py — persistent relationships.
6. event_rules.py — persistent events.
7. character_and_consistency_rules.py — character state, ambiguity, identity and consistency.
8. output_contract_and_examples.py — output contract and examples.

legacy_prompt_sections/__init__.py is the single ordered composition point.
Its STATIC_INSTRUCTIONS value is assembled by direct string concatenation.
The modules contain the original text, including whitespace and newlines; the
split was validated against the pre-change source before the branch was written.

## Stable public and runtime boundaries

- LLMWorldPromptBuilder.build_prompt(text, context) remains the public façade.
- LLMWorldContextRenderer.build_context(context) still owns all dynamic
  campaign/world rendering.
- The builder appends the dynamic narrative/context block after the static
  instruction body, as before.
- LLMWorldExtractor.extract() and its verified compatibility consumers remain
  unchanged.
- The durable propose() pipeline and LLMWorldProposalPromptBuilder are not modified.
- No parser, operation schema, domain validation, provider or authorization
  behavior is changed.

## Byte-for-byte regression gate

The new test tests/test_llm_world_prompt_sections.py fixes both the narrative
input and all dynamic context blocks. It compares the Git blob hash of the
complete rendered prompt against the output produced by the pre-decomposition
builder.

- Narrative fixture: Aldric entrega una llave de plata al personaje.
- Dynamic context: seven fixed section values, each uniquely labelled.
- Pre-decomposition complete-prompt blob ID:
  d1b3a5e3fbd93180cc05a9e8deb77389c9e6a4cc

The test uses Git's standard content-addressed blob hashing convention over
UTF-8 bytes. A change to prompt wording, ordering, spaces, line endings or
dynamic placement changes the expected digest and fails the test.

This is a structural compatibility gate, not a claim that the legacy prompt is
optimal or that the model produces better results. Any deliberate wording change
must be a separate, quality-measured change using representative live Ollama
probes. A source split alone does not reduce prompt tokens.

## Follow-up boundaries

This PR does not remove the legacy extract() API, the narrative-first
compatibility branch, the deprecated SillyTavern mutation route or snapshot
storage. Those removals still require consumer and usage/deprecation evidence.

The next useful prompt-related work, after this compatibility refactor is
integrated, is to assess the legacy extraction quality with representative
campaign fixtures and live-provider probes. Do not modify the active proposal
contract as part of that work.
