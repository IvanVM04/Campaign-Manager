# V3 action-preview runtime integration — 2026-11-22

## Scope and safety boundary

PR #297 connects the existing v3 action selector/checkpoint to the durable
planning lifecycle as an **opt-in shadow preview**. It does not promote v3 to
the authoritative interpreter. V2 remains responsible for the user-visible
turn result, mechanics, world proposals, operation validation and commit.

The environment flag is
`CAMPAIGN_MANAGER_PLAYER_TURN_V3_ACTION_SHADOW_ENABLED`. It accepts the
standard strict boolean spellings supported by `LLMSettings.from_env`, and
defaults to `false`. With the flag off, runtime composition does not create
the preview service and the existing 180-second planning lease is unchanged.

## Preview sequence

1. The existing durable turn is claimed and its normal v2 `TurnResolutionPlan`
   is prepared.
2. Before the durable row transitions to `prepared`, the optional preview
   reuses `IntentInterpreter._build_prompt` to preserve the same bounded
   context, same-chat history and exact current player evidence. It replaces
   only the instruction block with the shared holistic v3 prompt/schema.
3. The provider returns one structured interpretation. Exact evidence spans
   are aligned only when a unique literal occurrence makes the repair safe;
   the v3 decoder remains the strict validation boundary.
4. The preview builds a bounded `WorldContextProjection` with the active
   character and current location mandatory. Canonical entity references are
   resolved only within that selected visible world using
   `EntityReferenceResolver`. First-person agent forms are bound to the
   already selected active character; all other references require resolver
   evidence. Ambiguity and absence remain unresolved.
5. The backend action selector derives the action graph and returns at most
   one next candidate. The preview records the graph checkpoint but does not
   start, complete, fail or execute a node.
6. The repository persists the canonical checkpoint while the same planning
   lease is valid, with compare-and-swap on lifecycle state, lease token,
   context revision and prior checkpoint. The checkpoint is bound to the exact
   durable player input and the canonical v3 interpretation digest.

If a checkpoint already exists (for example, after a worker retry), the
preview is not regenerated; the exact stored graph/progress remains the
source of truth. This avoids replacing action identities or execution keys
with a different model generation.

## Lease and failure handling

With the preview enabled, the planning lease is extended to at least 600
seconds. The calculated budget also accounts for two intent-provider calls
(v2 plus v3), the configured mechanics and extraction timeouts, and a
two-minute margin. The flag-off path retains the old 180-second lease.

Provider, prompt, decoder, reference and selector failures are converted to
content-free stage/code diagnostics and do not replace the prepared v2 plan.
A failed optional checkpoint CAS/storage attempt is logged and skipped; the
subsequent authoritative v2 transition still must satisfy its own lease fence.
No utterance, prompt, completion, entity ID or raw exception message is added
to the new preview logs.

## Deliberate non-goals

- No v3 mechanics adjudication, dice rolls or action execution.
- No v3-generated proposal operations or world mutations.
- No world-fact policy or fact-receipt commit integration (PR #298).
- No generalized typed lookup for item definitions, item instances, resources
  or events; the first integration resolves canonical entity references only.
- No change to the existing v2 `intent_json` or historical decoder behavior.
- No claim of a real Ollama or SillyTavern acceptance run.

PR #299 will own end-to-end execution, callbacks/dependencies, resumable
clarifications and mechanics/technical outcomes. PR #300 owns the full
acceptance run and decision to keep v2 or consider a controlled cutover.
