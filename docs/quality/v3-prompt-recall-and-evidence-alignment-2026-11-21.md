# V3 prompt coverage and exact evidence alignment — 2026-11-21

**Implementation:** PR #294.  
**Scope:** diagnostic v3 shadow path only.  
**Production authority:** v2 remains the only production interpretation route; v3 has no authority over mechanics, world extraction, persistence or narration.

## 1. Problem addressed

The original v3 prompt strongly constrained trust, evidence and false positives, but did not prescribe a sufficiently explicit coverage pass for multi-clause turns. A conservative model could return valid JSON and still omit an independent proposition or a descriptive fact because it was not the most obvious playable action.

The graph-aware evaluator and its 20-scenario graph-gold corpus from PR #293 now make omissions and incorrect connections visible. This PR changes the prompt strategy and separately measures one deterministic source of span failures. It does not change graph gold to match observed model output.

## 2. Prompt strategy

Prompt version: `player-turn-v3-holistic-2026-11-21-pr294`.

The prompt remains one holistic interpretation call. It now requires a fixed internal coverage order:

1. Inventory every communicative/propositional clause across the whole turn.
2. Identify communicative acts without creating an act for every verb.
3. Emit an event frame for each explicit proposition, including non-executable, reported, observed, hypothetical and descriptive propositions.
4. Add only discourse edges supported by the wording, with the correct local endpoints.
5. Make a separate pass for explicit relationship and attribute candidates so an independent fact is not lost beside an unrelated failed action.
6. Add clarifications only for material ambiguity, without discarding the rest of the turn.
7. Review every clause for omissions and every node for unsupported additions.

The contrastive rules explicitly separate:
- independent clauses from conditional dependencies;
- a report or quotation from the player's own assertion/instruction;
- callback anchors from events;
- transfer roles from ownership/possession facts;
- refusal from a failed attempt;
- uncertain propositions from confirmed facts.

Examples are schematic and contrastive. The prompt does not contain literal utterances from the held-out corpora. It continues to require exact evidence, current-turn provenance, distinct speaker/agent/addressee/source roles, and backend-only authority.

## 3. Conservative evidence offset alignment

Algorithm version: `exact-unique-substring-v1`.

The shadow runner applies a narrow deterministic alignment step to the model's JSON before calling the unchanged `TurnInterpretationV3.from_json()` decoder.

- If the supplied offsets already select the exact supplied text in the current utterance, preserve them unchanged.
- If the offsets are wrong but the exact span text appears exactly once in the current utterance, replace only `start` and `end` with that unique occurrence's Unicode code-point offsets.
- If the exact text is absent, reject with `evidence_text_not_found`.
- If the exact text occurs more than once and the supplied offsets do not disambiguate it, reject with `ambiguous_evidence_text`.
- Empty/oversized span text, malformed JSON and invalid offset types are rejected.

There is no fuzzy matching, normalization, trimming, case folding, history lookup, context-based inference or choosing the first of several occurrences. The alignment step never invents span text and never turns history/narration into current-player evidence. After alignment, the strict v3 decoder still checks schema fields, offsets, literal grounding, ordering, local references, enums and graph structure.

The live diagnostics record only the alignment algorithm version and counts of realigned spans/scenarios. They do not record the span text or utterance.

## 4. Reproducibility and reports

The live graph and shadow reports now identify:
- prompt version and SHA-256 fingerprint (graph manifest);
- schema version and fingerprint (graph manifest);
- evidence alignment algorithm version;
- total realigned span count and number of scenarios requiring alignment;
- model/digest, Ollama version, available thinking/timeout metadata, commit provenance and provider-call counts.

Sampling parameters remain explicitly unclaimed where the provider contract does not expose their effective values. Raw prompts, completions, utterances, mentions and literal evidence are not added to aggregate reports.

## 5. Deterministic tests

The tests cover:
- presence of the complete-clause inventory, independent fact pass and final omission review in the prompt;
- contrastive rules for conditionals, reports/quotes, callbacks, transfer and refusal;
- repair of a uniquely located literal span after Unicode text;
- preservation of correct offsets where the same text occurs more than once;
- rejection of an ambiguous repeated phrase when offsets are wrong;
- rejection of span text absent from the current utterance;
- shadow-runner integration proving the corrected payload still passes the strict decoder and the repair count is exposed in the content-free shape.

Run:

```powershell
python -m pytest tests/test_player_turn_v3_shadow.py tests/test_player_turn_v3_graph_evaluation.py -q
ruff check tests/player_turn_interpretation_v3_shadow.py tests/test_player_turn_v3_shadow.py tests/test_real_llm_player_turn_v3_shadow.py tests/test_real_llm_player_turn_v3_graph.py
```

## 6. Live evaluation

Graph holdout (opt-in):

```powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_V3_GRAPH_ENABLE = "1"
python -m pytest -m real_llm tests/test_real_llm_player_turn_v3_graph.py -v -s
```

Optional single-scenario diagnostic:

```powershell
$env:CAMPAIGN_MANAGER_REAL_LLM_V3_GRAPH_SCENARIO_ID = "open_door_attempt"
```

The graph corpus remains held out. Compare the same model digest, Ollama version, thinking configuration, prompt/schema fingerprint and context. Inspect graph exact match, precision/recall by component and family, critical false positives, contract validity, evidence realignment counts, tokens and latency. Do not use a higher valid-span rate as a substitute for semantic graph accuracy.

## 7. Acceptance status and limits

| Evidence | Status at PR preparation |
|---|---|
| Deterministic prompt/alignment tests | Added; awaiting GitHub Actions |
| Ruff / Pyright / full CI | Awaiting GitHub Actions |
| Live Ollama v3 graph holdout | Not run in this change |
| Manual SillyTavern session | Not run |
| Production routing | v2 unchanged; v3 authority remains none |

A span repair can fix a uniquely recoverable offset error; it cannot recover omitted events, infer missing roles, resolve semantic ambiguity or correct a wrong predicate. Those remain prompt/model/representation issues measured by the graph scorer. Repeated literal spans intentionally fail closed. No rollout threshold is introduced by this PR.
