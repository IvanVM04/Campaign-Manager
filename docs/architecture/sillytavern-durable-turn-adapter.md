# SillyTavern durable turn adapter

**Status:** Implemented in PR #31.

## Request sequence

1. The generation interceptor identifies the latest user message and derives the stable external turn ID from chat identity and message index.
2. Before SillyTavern generates prose, it calls `POST /integration/turn/resolve`.
3. The backend uses the shared `DurableNativeTurnService` with adapter namespace `sillytavern`. The external turn ID is the durable idempotency key.
4. The coordinator plans structured consequences from player intent, validates them, and commits them with the resolution record and resulting campaign revision in one transaction.
5. The endpoint returns the current campaign context and committed resolution evidence. The extension injects both into SillyTavern's generation prompt.
6. After generation, the extension calls `POST /integration/turn/complete`. This stores the external narrative and completes the transcript projection; it does not apply domain operations.
7. If generation or completion fails after commit, the next generation reuses the same resolution. It does not replan or reapply consequences.

## Regeneration and swipes

A stable external turn ID represents the player message, not an individual assistant swipe. The first completed narrative is version 1. A different swipe creates the next transcript version and supersedes the prior narrative record. All versions reference the same committed domain outcome. No snapshot restore, reroll, or consequence replay occurs during a swipe.

Exact retries of a narrative version return the existing transcript. Reusing a version with different narrative content, submitting an older version, or skipping a version is rejected.

## Compatibility

- `GET /integration/turn/{external_turn_id}` continues to expose the active narrative version for local cache recovery.
- `POST /integration/turn` remains temporarily available for pre-PR31 extensions as a legacy compatibility adapter. It is not used by the current extension. New clients must call `/integration/turn/resolve` before generation and `/integration/turn/complete` afterward.
- If a turn already has a legacy active transcript but no durable resolution record, the new adapter treats it as a legacy replay: it preserves the existing world state and only versions the narrative. It does not infer or reapply consequences from the old narrative.

## Durable clarification continuation

1. If `POST /integration/turn/resolve` returns `lifecycle_state=awaiting_input`, it also returns a `pending_clarification_id`. The extension asks the player the clarification question; no transcript is completed yet.
2. When the player replies, the extension searches the recent chat history for the original action and checks its durable clarification state through `GET /integration/turn/{external_turn_id}/clarification`.
3. It submits the answer to `POST /integration/turn/clarification`, using the original challenge ID. The endpoint resumes the same resolution record and returns either another clarification question or committed resolution evidence.
4. Once the resolution is committed, SillyTavern generates the narrative. The extension completes the transcript using the original external turn ID and original player input, not the clarification answer as a new action.
5. The clarification-state endpoint exposes the active challenge and the last accepted challenge/answer. This lets the extension retry safely after a browser refresh or an interrupted generation without storing challenge tokens as local source-of-truth state.

The extension searches a bounded recent history (24 messages) when reconstructing the original action. The backend remains authoritative; if it cannot verify clarification state, generation is aborted rather than treating an unverified answer as a new action.

## Deliberate limitations

- This adapter uses automatic mechanics. Durable manual-roll submission is not yet integrated into the SillyTavern client.
- There is no background recovery worker. Recovery is request-driven through the same durable challenge and turn identities.
- A generation failure after consequence commit leaves the resolution in `narration_pending`; retrying the same clarification answer safely resumes narration without applying consequences again.
